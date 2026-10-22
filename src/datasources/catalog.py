"""Where each bulk source is published and how to find its latest release.

Verified on 2026-10-22:
- Companies House BasicCompanyData: https://download.companieshouse.gov.uk/en_output.html (monthly)
- Companies House PSC snapshot: https://download.companieshouse.gov.uk/en_pscdata.html (daily)
- UK Sanctions List (FCDO): https://sanctionslist.fcdo.gov.uk/docs/UK-Sanctions-List.txt
- ONS Postcode Directory: ArcGIS items owned by `ONSGeography_data` (quarterly)
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

import httpx

USER_AGENT = "Aethelburg/0.3 (local investigative research tool)"
CH_DOWNLOAD_BASE = "https://download.companieshouse.gov.uk/"
SANCTIONS_TXT_URL = "https://sanctionslist.fcdo.gov.uk/docs/UK-Sanctions-List.txt"
ARCGIS_SEARCH_URL = "https://www.arcgis.com/sharing/rest/search"
ARCGIS_ITEM_DATA_URL = "https://www.arcgis.com/sharing/rest/content/items/{item_id}/data"


@dataclass(frozen=True)
class SourceInfo:
    key: str
    title: str
    licence: str
    update_frequency: str
    # glob of the file to extract from the downloaded zip (None = not a zip)
    extract_pattern: str | None


@dataclass(frozen=True)
class Release:
    source: str
    version: str  # ISO date of the release
    url: str
    filename: str


SOURCES: dict[str, SourceInfo] = {
    "ch_companies": SourceInfo(
        "ch_companies",
        "Companies House - Basic Company Data",
        "Open Government Licence v3.0",
        "monthly",
        "BasicCompanyDataAsOneFile-*.csv",
    ),
    "ch_psc": SourceInfo(
        "ch_psc",
        "Companies House - Persons with Significant Control snapshot",
        "Open Government Licence v3.0",
        "daily",
        "persons-with-significant-control-snapshot-*.txt",
    ),
    "uk_sanctions": SourceInfo(
        "uk_sanctions",
        "UK Sanctions List (FCDO)",
        "Open Government Licence v3.0",
        "several times a week",
        None,
    ),
    "onspd": SourceInfo(
        "onspd",
        "ONS Postcode Directory",
        "Open Government Licence v3.0 (contains OS and Royal Mail data)",
        "quarterly",
        "Data/ONSPD_*_UK.csv",
    ),
}

_CH_COMPANIES_RE = re.compile(r'href="(BasicCompanyDataAsOneFile-(\d{4}-\d{2}-\d{2})\.zip)"')
_CH_PSC_RE = re.compile(r'href="(persons-with-significant-control-snapshot-(\d{4}-\d{2}-\d{2})\.zip)"')
_SANCTIONS_DATE_RE = re.compile(r"Report Date:\s*(\d{1,2}-[A-Za-z]{3}-\d{4})")
_ONSPD_TITLE_RE = re.compile(r"^ONS Postcode Directory \(([A-Za-z]+) (\d{4})\)$")


def latest_release(source: str, client: httpx.Client | None = None) -> Release:
    """Ask the publisher for the newest release of `source`."""
    own = client is None
    http = client or httpx.Client(timeout=30.0, headers={"User-Agent": USER_AGENT}, follow_redirects=True)
    try:
        if source == "ch_companies":
            return _from_ch_page(http, "en_output.html", _CH_COMPANIES_RE, source)
        if source == "ch_psc":
            return _from_ch_page(http, "en_pscdata.html", _CH_PSC_RE, source)
        if source == "uk_sanctions":
            return _sanctions_release(http)
        if source == "onspd":
            return _onspd_release(http)
        raise ValueError(f"Unknown source: {source}")
    finally:
        if own:
            http.close()


def _from_ch_page(http: httpx.Client, page: str, pattern: re.Pattern[str], source: str) -> Release:
    resp = http.get(CH_DOWNLOAD_BASE + page)
    resp.raise_for_status()
    matches = pattern.findall(resp.text)
    if not matches:
        raise RuntimeError(f"No release link found on {CH_DOWNLOAD_BASE}{page}; the page layout may have changed")
    filename, version = max(matches, key=lambda m: m[1])
    return Release(source, version, CH_DOWNLOAD_BASE + filename, filename)


def _sanctions_release(http: httpx.Client) -> Release:
    # The report date is on the first line; read only the first bytes
    resp = http.get(SANCTIONS_TXT_URL, headers={"Range": "bytes=0-199"})
    resp.raise_for_status()
    match = _SANCTIONS_DATE_RE.search(resp.text)
    if not match:
        raise RuntimeError("UK Sanctions List: report date not found in the file header")
    version = datetime.strptime(match.group(1), "%d-%b-%Y").strftime("%Y-%m-%d")
    return Release("uk_sanctions", version, SANCTIONS_TXT_URL, "UK-Sanctions-List.txt")


def _onspd_release(http: httpx.Client) -> Release:
    resp = http.get(
        ARCGIS_SEARCH_URL,
        params={
            "q": 'title:"ONS Postcode Directory" AND owner:ONSGeography_data AND type:"CSV Collection"',
            "sortField": "modified",
            "sortOrder": "desc",
            "num": 50,
            "f": "json",
        },
    )
    resp.raise_for_status()
    best: tuple[str, str] | None = None  # (version, item id)
    for item in resp.json().get("results", []):
        match = _ONSPD_TITLE_RE.match(item.get("title", ""))  # skips "... User Guide" items
        if not match:
            continue
        version = datetime.strptime(f"1 {match.group(1)} {match.group(2)}", "%d %B %Y").strftime("%Y-%m-%d")
        if best is None or version > best[0]:
            best = (version, item["id"])
    if best is None:
        raise RuntimeError("ONSPD: no 'ONS Postcode Directory (Month Year)' CSV collection found on ArcGIS")
    version, item_id = best
    month = datetime.strptime(version, "%Y-%m-%d").strftime("%b").upper()
    return Release("onspd", version, ARCGIS_ITEM_DATA_URL.format(item_id=item_id), f"ONSPD_{month}_{version[:4]}.zip")
