"""Change history of the companies in the database (`company_changes`).

Every update (monthly bulk import, Streaming API, "Update from CH") overwrites the current
registry fields of a company. Before the overwrite `upsert_company_record` passes the stored
row and the merged record here, and every difference in a tracked field becomes one row:
what changed, the old and the new value, when it was observed and from which source.

Officer appointments and PSC statements are recorded too, but only when they appear or end
after the company had already been loaded: the first load of a company is not a change.
"""
from __future__ import annotations

import csv
import io
import re
from typing import Any

# change type -> registry columns compared together (one row per type, values joined)
COMPANY_FIELDS: dict[str, tuple[str, ...]] = {
    "NAME_CHANGED": ("company_name",),
    "STATUS_CHANGED": ("company_status",),
    "ADDRESS_CHANGED": (
        "reg_address_care_of",
        "reg_address_po_box",
        "reg_address_line1",
        "reg_address_line2",
        "reg_address_post_town",
        "reg_address_county",
        "reg_address_country",
        "reg_address_postcode",
    ),
    "CATEGORY_CHANGED": ("company_category",),
    "SIC_CHANGED": ("sic_code_1", "sic_code_2", "sic_code_3", "sic_code_4"),
    "DISSOLUTION_DATE_CHANGED": ("dissolution_date",),
    "ACCOUNTS_FILED": ("accounts_last_made_up_date",),
    "CONFIRMATION_STATEMENT_FILED": ("conf_stmt_last_made_up_date",),
    "CHARGES_CHANGED": ("mortgages_num_charges",),
}

CHANGE_TYPES: tuple[str, ...] = (
    *COMPANY_FIELDS,
    "OFFICER_APPOINTED",
    "OFFICER_RESIGNED",
    "PSC_ADDED",
    "PSC_CEASED",
)

# Types where an empty old value still means an event: first accounts, dissolution
_FIRST_VALUE_IS_A_CHANGE = frozenset({"DISSOLUTION_DATE_CHANGED", "ACCOUNTS_FILED", "CONFIRMATION_STATEMENT_FILED"})

# Placeholder names given to companies first seen through a PSC statement
_STUB_PREFIXES = ("HISTORICAL UK ENTITY ", "OVERSEAS ENTITY ")


_PUNCT_RE = re.compile(r"[^\w]+")


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _joined(rec: Any, columns: tuple[str, ...]) -> str:
    return ", ".join(v for v in (_text(rec[c]) for c in columns) if v)


def _comparable(value: str) -> str:
    """Bulk files write `71-75 SHELTON STREET`, the API `71-75 Shelton Street`: same value."""
    return _PUNCT_RE.sub(" ", value.casefold()).strip()


def _differs(change_type: str, previous: Any, merged: dict[str, Any], old: str, new: str) -> bool:
    if change_type == "ADDRESS_CHANGED":
        # county and country are filled differently by the bulk product and the API: compare
        # the ADR-015 fingerprint (postcode | house number | street keyword) when both have one
        old_fp, new_fp = _text(previous["address_fingerprint"]), _text(merged.get("address_fingerprint"))
        if old_fp and new_fp:
            return old_fp != new_fp
    return _comparable(old) != _comparable(new)


def record_company_changes(
    conn: Any, previous: Any, merged: dict[str, Any], source_id: str | None, observed_at: str
) -> int:
    """Write one row per tracked field that differs between the stored row and the merged record.

    Values missing from a partial update (an API profile without SIC codes, a Streaming event)
    have already been filled from the stored row by the caller, so they never count as changes.
    A stub company (created from a PSC statement) taking its real name and address is not a change.
    """
    if _text(previous["company_name"]).startswith(_STUB_PREFIXES):
        return 0
    written = 0
    for change_type, columns in COMPANY_FIELDS.items():
        old, new = _joined(previous, columns), _joined(merged, columns)
        if not new or not _differs(change_type, previous, merged, old, new):
            continue
        if not old and change_type not in _FIRST_VALUE_IS_A_CHANGE:
            continue  # a value the earlier source did not have (e.g. the API adding a category) is not a change
        effective = None
        if change_type == "NAME_CHANGED":
            effective = merged.get("prev_name_1_date")
        elif change_type == "STATUS_CHANGED" and merged.get("dissolution_date"):
            effective = merged["dissolution_date"]
        elif change_type in ("ACCOUNTS_FILED", "CONFIRMATION_STATEMENT_FILED"):
            effective = new
        add_change(conn, merged["company_number"], change_type, old or None, new, source_id, observed_at, effective)
        written += 1
    return written


def add_change(
    conn: Any,
    company_number: str,
    change_type: str,
    old_value: str | None,
    new_value: str | None,
    source_id: str | None,
    observed_at: str,
    effective_date: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO company_changes
            (company_number, change_type, old_value, new_value, effective_date, observed_at, source_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (company_number, change_type, old_value, new_value, effective_date, observed_at, source_id),
    )


def list_changes(
    conn: Any,
    company_number: str | None = None,
    change_type: str | None = None,
    subset_only: bool = False,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Most recent changes first, with the source label (`<source type> <version>`)."""
    where, params = [], []
    if company_number:
        where.append("cc.company_number = ?")
        params.append(company_number)
    if change_type:
        where.append("cc.change_type = ?")
        params.append(change_type)
    if subset_only:
        where.append("cc.company_number IN (SELECT company_number FROM subset_members)")
    sql = f"""
        SELECT cc.id, cc.company_number, c.company_name, cc.change_type, cc.old_value, cc.new_value,
               cc.effective_date, cc.observed_at,
               TRIM(COALESCE(ds.source_type, '') || ' ' || COALESCE(ds.source_version, '')) AS source
        FROM company_changes cc
        LEFT JOIN companies c ON c.company_number = cc.company_number
        LEFT JOIN data_sources ds ON ds.id = cc.source_id
        {'WHERE ' + ' AND '.join(where) if where else ''}
        ORDER BY cc.observed_at DESC, cc.id DESC
        LIMIT ?
    """
    return [dict(r) for r in conn.execute(sql, [*params, max(1, min(limit, 100_000))])]


def change_counts(conn: Any) -> dict[str, int]:
    return {r[0]: r[1] for r in conn.execute("SELECT change_type, COUNT(*) FROM company_changes GROUP BY change_type")}


def changes_csv(rows: list[dict[str, Any]]) -> bytes:
    buf = io.StringIO()
    fields = ["company_number", "company_name", "change_type", "old_value", "new_value",
              "effective_date", "observed_at", "source"]
    writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8-sig")
