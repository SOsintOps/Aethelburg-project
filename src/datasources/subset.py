"""Light index of the whole register and selection of the subset that is fully imported.

Criteria (configured in `config/subset.toml`, overridable per user):
- risk links: sanctions (company numbers, names), ICIJ name matches, corporate PSC registered
  outside the UK or offshore, super-secure PSC; optionally one hop through shared PSC controllers
- mass addresses: registered address shared by >= N companies
- recent incorporations: incorporated in the last N years

Everything streams from disk; nothing proportional to the register is held in memory except
sets of selected company numbers and controller keys.
"""
from __future__ import annotations

import csv
import re
import tomllib
from collections import defaultdict
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field, fields
from datetime import date, datetime
from pathlib import Path
from typing import Any

import orjson

from config.user_config import PROJECT_ROOT, load_user_config
from src.core.normalizer import compute_address_fingerprint, normalize_name, normalize_postcode
from src.datasources.runs import checkpoint, finish_run, start_run
from src.etl.import_psc import _is_offshore_jurisdiction
from src.etl.import_sanctions import parse_uk_sanctions_row

Progress = Callable[[str, int], None]  # (stage, rows processed)
_BATCH = 20_000
_MIN_NAME_MATCH_LEN = 8  # shorter fingerprints ("ABC LTD") match too many unrelated names

_UK_TOKENS = (
    "england", "wales", "scotland", "northern ireland", "united kingdom", "great britain",
    "britain", "u.k", "uk", "gb", "companies house", "cardiff", "edinburgh", "belfast", "london",
)


_INDEX_DDL = {  # same definitions as the schema in db_service.py
    "idx_company_index_name": "CREATE INDEX IF NOT EXISTS idx_company_index_name ON company_index(company_name)",
    "idx_company_index_name_fp": "CREATE INDEX IF NOT EXISTS idx_company_index_name_fp ON company_index(name_fingerprint)",
    "idx_company_index_address": (
        "CREATE INDEX IF NOT EXISTS idx_company_index_address ON company_index(address_fingerprint)"
    ),
    "idx_company_index_incorporated": (
        "CREATE INDEX IF NOT EXISTS idx_company_index_incorporated ON company_index(incorporation_date)"
    ),
}


@dataclass
class SubsetConfig:
    risk_links: bool = True
    risk_links_one_hop: bool = True
    mass_address: bool = True
    mass_address_min_companies: int = 50
    recent: bool = True
    recent_years: int = 3
    # "and": only companies that are both recent and at a mass address; "or": either
    broad_criteria_mode: str = "and"
    broad_criteria_active_only: bool = True
    # Companies with at least one individual PSC of these nationalities (empty list = off)
    psc_nationalities: list[str] = field(default_factory=lambda: ["Italian"])

    @classmethod
    def load(cls) -> SubsetConfig:
        values: dict[str, Any] = {}
        defaults = PROJECT_ROOT / "config" / "subset.toml"
        if defaults.exists():
            values.update(tomllib.loads(defaults.read_text(encoding="utf-8")))
        user = load_user_config()
        values.update({k[len("subset_"):]: v for k, v in user.items() if k.startswith("subset_")})
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in values.items() if k in known})


# ---------------------------------------------------------------------- #
# LIGHT INDEX                                                            #
# ---------------------------------------------------------------------- #


def build_company_index(conn: Any, csv_path: Path, version: str, progress: Progress | None = None) -> int:
    """Load every company of `BasicCompanyDataAsOneFile` into `company_index` (resumable)."""
    run = start_run(conn, "company_index", "ch_companies", version, str(csv_path))
    # Secondary indexes make millions of inserts crawl; rebuild them once at the end
    for name in _INDEX_DDL:
        conn.execute(f"DROP INDEX IF EXISTS {name}")
    conn.commit()
    batch: list[tuple[Any, ...]] = []
    for idx, row in enumerate(_iter_company_rows(csv_path)):
        if idx < run.resume_from:
            continue
        number = row.get("CompanyNumber", "").upper()
        name = row.get("CompanyName", "")
        run.rows_read = idx + 1
        if not number or not name:
            continue
        postcode = normalize_postcode(row.get("RegAddress.PostCode")) or None
        batch.append(
            (
                number,
                name,
                normalize_name(name, is_company=True),
                postcode,
                compute_address_fingerprint(
                    postcode, row.get("RegAddress.AddressLine1"), row.get("RegAddress.AddressLine2"),
                    row.get("RegAddress.PostTown"),
                ) or None,
                row.get("CompanyStatus") or None,
                row.get("CompanyCategory") or None,
                _iso_date(row.get("IncorporationDate")),
                version,
            )
        )
        if len(batch) >= _BATCH:
            _write_index(conn, batch, run)
            if progress:
                progress("index", run.rows_read)
    _write_index(conn, batch, run)
    if progress:
        progress("index_rebuild", run.rows_written)
    for ddl in _INDEX_DDL.values():
        conn.execute(ddl)
    finish_run(conn, run)
    return run.rows_written


def _write_index(conn: Any, batch: list[tuple[Any, ...]], run: Any) -> None:
    if batch:
        conn.executemany(
            """
            INSERT OR REPLACE INTO company_index
                (company_number, company_name, name_fingerprint, postcode, address_fingerprint,
                 company_status, company_category, incorporation_date, source_version)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            batch,
        )
        run.rows_written += len(batch)
        batch.clear()
    checkpoint(conn, run)


# ---------------------------------------------------------------------- #
# SELECTION                                                              #
# ---------------------------------------------------------------------- #


def select_subset(
    conn: Any,
    cfg: SubsetConfig,
    psc_path: Path | None,
    sanctions_path: Path | None,
    icij_dir: Path | None,
    progress: Progress | None = None,
) -> dict[str, int]:
    """Fill `subset_members` from `company_index` and the bulk files; returns counts per criterion."""
    reasons: dict[str, set[str]] = defaultdict(set)

    if cfg.risk_links:
        if sanctions_path and sanctions_path.exists():
            numbers, names = _sanctioned(sanctions_path)
            for n in numbers:
                reasons[n].add("sanctions")
            for n in _match_names(conn, names):
                reasons[n].add("sanctions_name")
        if icij_dir and icij_dir.is_dir():
            for n in _match_names(conn, _icij_names(icij_dir)):
                reasons[n].add("icij")

    nationalities = _nationality_set(cfg.psc_nationalities)
    if psc_path and psc_path.exists() and (cfg.risk_links or nationalities):
        risky, by_nationality = _scan_psc(psc_path, nationalities, progress)
        for n, why in by_nationality.items():
            reasons[n].update(why)
        if cfg.risk_links:
            for n, why in risky.items():
                reasons[n].update(why)
            if cfg.risk_links_one_hop and risky:
                keys = _controllers_of(psc_path, set(risky), progress)
                for n in _companies_of_controllers(psc_path, keys, progress):
                    if n not in risky:
                        reasons[n].add("psc_one_hop")

    active_sql = "AND company_status NOT LIKE '%Dissolved%'" if cfg.broad_criteria_active_only else ""
    mass: set[str] = set()
    recent: set[str] = set()
    if cfg.mass_address:
        mass = {
            n for (n,) in conn.execute(
                f"""
                SELECT company_number FROM company_index
                WHERE address_fingerprint IN (
                    SELECT address_fingerprint FROM company_index
                    WHERE address_fingerprint IS NOT NULL
                    GROUP BY address_fingerprint HAVING COUNT(*) >= ?
                ) {active_sql}
                """,
                (int(cfg.mass_address_min_companies),),
            )
        }
    if cfg.recent:
        since = date.today().replace(year=date.today().year - int(cfg.recent_years)).isoformat()
        recent = {
            n for (n,) in conn.execute(
                f"SELECT company_number FROM company_index WHERE incorporation_date >= ? {active_sql}", (since,)
            )
        }
    if cfg.mass_address and cfg.recent and cfg.broad_criteria_mode == "and":
        mass = recent = mass & recent  # recent shell-like registrations only
    for n in mass:
        reasons[n].add("mass_address")
    for n in recent:
        reasons[n].add("recent")

    conn.execute("DELETE FROM subset_members")
    conn.executemany(
        "INSERT INTO subset_members (company_number, reasons) VALUES (?, ?)",
        ((n, ",".join(sorted(r))) for n, r in reasons.items()),
    )
    conn.commit()

    counts: dict[str, int] = defaultdict(int)
    for r in reasons.values():
        for reason in r:
            counts[reason] += 1
    counts["total"] = len(reasons)
    return dict(counts)


def _sanctioned(path: Path) -> tuple[set[str], set[str]]:
    numbers: set[str] = set()
    names: set[str] = set()
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        if not fh.readline().startswith("Report Date:"):
            fh.seek(0)
        reader = csv.reader(fh, delimiter=";")
        next(reader, None)
        for row in reader:
            parsed = parse_uk_sanctions_row(row)
            if not parsed:
                continue
            numbers.update(n for n in parsed["registration_numbers"] if len(n) == 8)
            if parsed.get("entity_type") == "Entity" and parsed.get("full_name"):
                names.add(normalize_name(parsed["full_name"], is_company=True))
    return numbers, names


def _icij_names(icij_dir: Path) -> set[str]:
    """Normalised names of ICIJ entities and of officers that are companies."""
    names: set[str] = set()
    for filename in ("nodes-entities.csv", "nodes-officers.csv"):
        path = icij_dir / filename
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for row in csv.DictReader(fh):
                name = row.get("name") or ""
                if filename == "nodes-officers.csv" and not _looks_like_company(name):
                    continue
                names.add(normalize_name(name, is_company=True))
    return names


def _match_names(conn: Any, names: set[str]) -> set[str]:
    wanted = [n for n in names if n and len(n) >= _MIN_NAME_MATCH_LEN]
    found: set[str] = set()
    for i in range(0, len(wanted), 900):
        chunk = wanted[i:i + 900]
        placeholders = ",".join("?" for _ in chunk)
        found.update(
            r[0] for r in conn.execute(
                f"SELECT company_number FROM company_index WHERE name_fingerprint IN ({placeholders})", chunk
            )
        )
    return found


# ---------------------------------------------------------------------- #
# PSC PASSES                                                             #
# ---------------------------------------------------------------------- #


def _scan_psc(
    path: Path, nationalities: dict[str, str], progress: Progress | None
) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """One pass: risk reasons per company, and companies with a PSC of a wanted nationality."""
    risky: dict[str, set[str]] = defaultdict(set)
    by_nationality: dict[str, set[str]] = defaultdict(set)
    for idx, (number, data) in enumerate(_iter_psc(path)):
        reason = psc_risk_reason(data)
        if reason:
            risky[number].add(reason)
        if nationalities:
            label = nationality_match(data.get("nationality"), nationalities)
            if label:
                by_nationality[number].add(f"nationality_{label}")
        if progress and idx % 500_000 == 0:
            progress("psc_scan", idx)
    return risky, by_nationality


def psc_risk_reason(data: dict[str, Any]) -> str | None:
    """Why a PSC statement makes its company a risk link (None if it does not)."""
    kind = data.get("kind") or ""
    if "super-secure" in kind:
        return "super_secure_psc"
    if "corporate-entity" in kind or "legal-person" in kind:
        jurisdiction = _jurisdiction(data)
        if _is_offshore_jurisdiction(jurisdiction):
            return "offshore_psc"
        if jurisdiction and not _is_uk(jurisdiction):
            return "foreign_psc"
    return None


# Country names written instead of the demonym in the nationality field
_NATIONALITY_ALIASES = {"italian": ("italy", "italia", "italiana", "italiano")}


def _nationality_set(wanted: list[str]) -> dict[str, str]:
    """Lower-case spellings -> label used in the reason (`nationality_italian`)."""
    spellings: dict[str, str] = {}
    for value in wanted or []:
        label = value.strip().lower()
        if not label:
            continue
        spellings[label] = label
        for alias in _NATIONALITY_ALIASES.get(label, ()):
            spellings[alias] = label
    return spellings


def nationality_match(nationality: str | None, spellings: dict[str, str]) -> str | None:
    """`British,Italian` matches `italian`; the field is a comma-separated list of free text."""
    if not nationality or not spellings:
        return None
    for part in re.split(r"[,/;]", nationality.lower()):
        label = spellings.get(part.strip())
        if label:
            return label
    return None


def _controllers_of(path: Path, companies: set[str], progress: Progress | None) -> set[str]:
    keys: set[str] = set()
    for idx, (number, data) in enumerate(_iter_psc(path)):
        if number in companies:
            key = _controller_key(data)
            if key:
                keys.add(key)
        if progress and idx % 500_000 == 0:
            progress("psc_controllers", idx)
    return keys


def _companies_of_controllers(path: Path, keys: set[str], progress: Progress | None) -> set[str]:
    found: set[str] = set()
    for idx, (number, data) in enumerate(_iter_psc(path)):
        if _controller_key(data) in keys:
            found.add(number)
        if progress and idx % 500_000 == 0:
            progress("psc_one_hop", idx)
    return found


def _controller_key(data: dict[str, Any]) -> str | None:
    """Identity of a PSC controller across companies: name + birth month (people) or registration (entities)."""
    kind = data.get("kind") or ""
    name = data.get("name")
    if not name or "super-secure" in kind:
        return None
    if "individual" in kind:
        dob = data.get("date_of_birth") or {}
        if not dob.get("year"):
            return None  # a bare name would merge unrelated people
        return f"p|{normalize_name(name)}|{dob.get('year')}-{dob.get('month')}"
    ident = data.get("identification") or {}
    return f"e|{normalize_name(name, is_company=True)}|{(ident.get('registration_number') or '').strip().upper()}"


def _jurisdiction(data: dict[str, Any]) -> str:
    ident = data.get("identification") or {}
    addr = data.get("address") or {}
    return (ident.get("country_registered") or ident.get("place_registered") or addr.get("country") or "").strip()


def _is_uk(text: str) -> bool:
    # whole-word match: "Ukraine" must not count as "uk"
    low = " " + "".join(ch if ch.isalnum() or ch == "." else " " for ch in text.lower()) + " "
    return any(f" {tok} " in low for tok in _UK_TOKENS)


def _looks_like_company(name: str) -> bool:
    upper = f" {name.upper()} "
    return any(s in upper for s in (" LTD", " LIMITED", " LLP", " PLC", " INC", " CORP", " S.A", " LLC", " HOLDINGS"))


def _iter_psc(path: Path) -> Iterator[tuple[str, dict[str, Any]]]:
    with path.open("rb") as fh:
        for line in fh:
            try:
                obj = orjson.loads(line)
            except orjson.JSONDecodeError:
                continue
            number = (obj.get("company_number") or "").strip().upper()
            data = obj.get("data")
            if number and isinstance(data, dict):
                yield number, data


def _iter_company_rows(csv_path: Path) -> Iterator[dict[str, str]]:
    with csv_path.open("r", encoding="utf-8", errors="replace", newline="") as fh:
        reader = csv.reader(fh)
        header = [h.strip() for h in next(reader)]
        for values in reader:
            yield {k: v.strip() for k, v in zip(header, values, strict=False)}


def _iso_date(val: str | None) -> str | None:
    if not val:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(val.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None
