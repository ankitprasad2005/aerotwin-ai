"""Airports Authority of India (AAI) monthly "Traffic News": aircraft movements, passengers and freight per airport.

AAI publishes each month as PDF annexures at aai.aero. Annexure II (movements), III (passengers) and IV (freight)
each have a part A (international), B (domestic) and C (total) listing every airport with the month's figure,
the same month a year earlier and the percentage change (then the same three for the financial year to date).
The tables are text PDFs; rows are read with pdfplumber. Anything unreadable fails the snapshot: figures are
never estimated.
"""
import asyncio
import calendar
import io
import re
from pathlib import Path
from urllib.parse import urljoin

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.datasets.common import DatasetError, FetchOutcome, bulk_upsert, download, run_source, save_raw, sha256_hex, utcnow
from app.datasets.dgca import MONTHS
from app.models.external import AirportTrafficMonthly, DatasetSnapshot, IndiaAirport

SOURCE = "aai_traffic"
INDEX_URL = "https://www.aai.aero/en/business-opportunities/aai-traffic-news"
# How many of the newest complete months are loaded.
MAX_MONTHS = 2

# Annexure number -> measure.
MOVEMENTS, PASSENGERS, FREIGHT = 2, 3, 4
ANNEXES = (MOVEMENTS, PASSENGERS, FREIGHT)
MONTH_NAMES = dict(enumerate(calendar.month_name))
SCOPE_INTERNATIONAL, SCOPE_DOMESTIC, SCOPE_TOTAL = "A", "B", "C"

_LINK = re.compile(
    r"""href\s*=\s*["']([^"']*traffic-news/([A-Za-z]+)2k(\d{2})Ann?ex_?(\d)(?:_\d+)?\.pdf)["']""", re.IGNORECASE
)
_SECTION = re.compile(r"ANNEXURE-\s*(?:IV|III|II|I)\s+([ABC])\b")
_NUMBER = re.compile(r"^-?\d[\d.]*$")
_PERCENT = re.compile(r"^(-?\d[\d.]*)%$")
_NAME_TOKEN = re.compile(r"^[A-Z0-9.()&'/,\-]+$")
_NAME_TAIL = re.compile(r"[A-Z][A-Z0-9.()&'/,\-]*$")

# AAI airport name (upper case, as published) -> IATA code. None: no scheduled-service IATA code exists
# (air force enclaves, aerodromes without a code) so those rows are kept by name only.
AAI_IATA: dict[str, str | None] = {
    "ADAMPUR (JALANDHAR)": "AIP", "AGARTALA": "IXA", "AGATTI": "AGX", "AGRA": "AGR", "AHMEDABAD": "AMD",
    "AIZAWL (LENGPUI)": "AJL", "ALIGARH": "HRH", "AMBIKAPUR": "AHA", "AMRAVATI": "AVR", "AMRITSAR": "ATQ",
    "AURANGABAD": "IXU", "AYODHYA": "AYJ", "AZAMGARH": "AZH", "BAGDOGRA": "IXB", "BARAPANI (SHILLONG)": "SHL",
    "BAREILLY": "BEK", "BELAGAVI": "IXG", "BENGALURU (BIAL)": "BLR", "BENGALURU (HAL)": None,
    "BHATINDA": "BUP", "BHAVNAGAR": "BHU", "BHOPAL": "BHO", "BHUBANESWAR": "BBI",
    "BHUJ": "BHJ", "BHUNTAR (KULLU MANALI)": "KUU", "BIDAR": "IXX", "BIKANER": "BKB", "BILASPUR": "PAB",
    "CHANDIGARH": "IXC", "CHENNAI": "MAA", "CHITRAKOOT": "CWK", "COCHIN": "COK", "COIMBATORE": "CJB",
    "COOCHBEHER": "COH", "CUDDAPAH": "CDP", "DAMAN": "NMB", "DARBHANGA": "DBR", "DATIA": None,
    "DEHRADUN": "DED", "DELHI": "DEL", "DEOGHAR": "DGH", "DIMAPUR": "DMU", "DIU": "DIU",
    "DURGAPUR": "RDP", "GAGGAL (KANGRA)": "DHM", "GAYA": "GAY", "GOA (DABOLIM)": "GOI",
    "GOA (MOPA)": "GOX", "GONDIA": "GDB", "GORAKHPUR": "GOP", "GUWAHATI": "GAU", "GWALIOR": "GWL",
    "HINDON": "HDO", "HISAR": "HSS", "HUBBALI": "HBX", "HYDERABAD (BEGUMPET)": "BPM", "HYDERABAD (GHIAL)": "HYD",
    "IMPHAL": "IMF", "INDORE": "IDR", "ITANAGAR (HOLONGI)": "HGI", "JABALPUR": "JLR", "JAGDALPUR": "JGB",
    "JAIPUR": "JAI", "JAISALMER": "JSA", "JALGAON": "JLG", "JAMMU": "IXJ", "JAMNAGAR": "JGA",
    "JAMSHEDPUR": "IXW", "JEYPORE": "PYB", "JHARSUGUDA": "JRG", "JODHPUR": "JDH", "JORHAT": "JRH",
    "JUHU": None, "KALABURAGI (GULBARGA)": "GBI", "KANDLA": "IXY", "KANNUR (KIAL)": "CNN",
    "KANPUR (CHAKERI)": "KNU", "KANPUR (CIVIL)": None, "KESHOD (JUNAGARH)": "IXK", "KHAJURAHO": "HJR",
    "KISHANGARH": "KQH", "KOCHI": "COK", "KOLHAPUR": "KLH", "KOLKATA": "CCU", "KOTA": "KTU",
    "KOZHIKODE": "CCJ", "KURNOOL": "KJB", "KUSHINAGAR": "KBK", "LAKHIMPUR (LILABARI)": "IXI", "LEH": "IXL",
    "LUCKNOW": "LKO", "LUDHIANA (HALWARA)": "HWR", "MADURAI": "IXM", "MANGALURU": "IXE",
    "MOHANBARI (DIBRUGARH)": "DIB", "MORADABAD": "MZS", "MUMBAI (MIAL)": "BOM", "MUNDRA": None,
    "MYSURU": "MYQ", "NAGPUR": "NAG", "NANDED": "NDC", "NASIK (HAL OZAR)": "ISK", "NAVI MUMBAI (NMIAL)": "NMI",
    "NOIDA (NIAL)": "DXN", "PAKYONG": "PYG", "PANTNAGAR": "PGH", "PASIGHAT": "IXT", "PATHANKOT": "IXP",
    "PATNA": "PAT", "PITHORAGARH": None, "PORBANDAR": "PBD", "PORT BLAIR": "IXZ", "PRAYAGRAJ": "IXD",
    "PUDUCHERRY": "PNY", "PUNE": "PNQ", "PURNEA": None, "RAIPUR": "RPR", "RAJAHMUNDRY": "RJA",
    "RAJKOT (HIRASAR)": "HSR", "RANCHI": "IXR", "REWA": "REW", "ROURKELA": "RRK", "RUPSI": "RUP",
    "SAFDARJUNG": None, "SALEM": "SXV", "SATNA": "TNI", "SHIMLA": "SLV", "SHIRDI": "SAG",
    "SHIVAMOGGA": "RQY", "SHOLAPUR": "SSE", "SHRAVASTI": "VSV", "SILCHAR": "IXS", "SINDHUDURG": "SDW",
    "SRINAGAR": "SXR", "SURAT": "STV", "TEZPUR": "TEZ", "TEZU": "TEI", "THIRUVANANTHAPURAM": "TRV",
    "TIRUCHIRAPPALLI": "TRZ", "TIRUPATI": "TIR", "TUTICORIN": "TCR", "UDAIPUR": "UDR", "UTKELA": "UKE",
    "VADODARA": "BDQ", "VARANASI": "VNS", "VIJAYAWADA": "VGA", "VIJAYANAGAR": "VDY",
    "VISAKHAPATNAM (GVIAL)": "VTZ", "ZIRO": "ZER",
}


# The annexures spell a few airports differently from table to table.
NAME_ALIASES = {"DELHI (DIAL)": "DELHI", "GOA": "GOA (DABOLIM)"}


def normalize_name(name: str) -> str:
    """Canonical airport name: stray leading glyphs dropped, one space before "(", known aliases folded."""
    name = re.sub(r"^[^A-Z0-9]+", "", name)
    name = re.sub(r"\s*\(", " (", name)
    name = " ".join(name.split())
    return NAME_ALIASES.get(name, name)


def discover_reports(html: str, page_url: str = INDEX_URL) -> dict[str, dict[int, str]]:
    """Annexure PDF links by month: {"2026-08": {1: url, 2: url, ...}}. Months with an unknown name are skipped."""
    reports: dict[str, dict[int, str]] = {}
    for href, month_name, year, annex in _LINK.findall(html):
        month = MONTHS.get(month_name.lower())
        if month is None:
            continue
        period = f"20{year}-{month:02d}"
        reports.setdefault(period, {}).setdefault(int(annex), urljoin(page_url, href.replace("&amp;", "&")))
    return reports


def latest_complete_periods(reports: dict[str, dict[int, str]], count: int = MAX_MONTHS) -> list[str]:
    """The newest `count` periods that link every annexure we read, newest first."""
    complete = [period for period, annexes in reports.items() if all(a in annexes for a in ANNEXES)]
    return sorted(complete, reverse=True)[:count]


def extract_pages(content: bytes) -> list[str]:
    import pdfplumber  # imported lazily: only the AAI refresh needs it

    with pdfplumber.open(io.BytesIO(content)) as pdf:
        return [(page.extract_text() or "") for page in pdf.pages]


def _to_number(token: str) -> float:
    return float(token)


def parse_row(line: str) -> tuple[str, float, float | None] | None:
    """(airport name, month value, year-on-year percent or None) from one table row, else None.

    A row is a serial number, a Hindi name (often garbled by the PDF font), the English upper-case name and six
    figures: month, same month last year, % change, year to date, last year's, % change. "-" means AAI did not
    publish a percentage (the base was zero or the change is not meaningful).
    """
    tokens = line.split()
    if len(tokens) < 8 or not tokens[0][0].isdigit():
        return None
    month, previous, change, ytd, ytd_previous, ytd_change = tokens[-6:]
    figures_ok = all(_NUMBER.match(t) for t in (month, previous, ytd, ytd_previous))
    changes_ok = all(_PERCENT.match(t) or t == "-" for t in (change, ytd_change))
    if not (figures_ok and changes_ok):
        return None
    words: list[str] = []
    unclosed = 0  # ")" seen (reading right to left) whose "(" is still to come
    for token in reversed(tokens[:-6]):
        # Hindi glyphs the PDF font garbles into ASCII look like names: "12C", "F)", "U". Names never start with a
        # digit, have at least two letters per word, and keep their brackets balanced.
        delta = token.count(")") - token.count("(")
        usable = (
            _NAME_TOKEN.match(token) and len(re.findall("[A-Z]", token)) > 1 and not token[0].isdigit()
            and not (delta > 0 and words and unclosed == 0)
        )
        if usable:
            words.append(token)
            unclosed = max(unclosed + delta, 0)
            continue
        tail = _NAME_TAIL.search(token)  # Hindi glyphs glued to the English name, e.g. "\u0941JAMMU"
        if tail and tail.start() > 0 and not _NAME_TOKEN.match(token) and len(re.findall("[A-Z]", tail.group(0))) > 1:
            words.append(tail.group(0))
        break
    while words and words[-1].startswith("("):  # a name never opens with a bracket: that is debris too
        words.pop()
    if not words:
        return None
    pct = _PERCENT.match(change)
    return normalize_name(" ".join(reversed(words))), _to_number(month), float(pct.group(1)) if pct else None


def parse_annex(pages: list[str]) -> dict[str, dict[str, tuple[float, float | None]]]:
    """{scope: {airport name: (month value, yoy pct)}} for scope A (international), B (domestic) and C (total).

    A page without its own "ANNEXURE-x A/B/C" heading continues the previous part. The grand-total rows have no
    serial number and are skipped, so only airports are returned.
    """
    result: dict[str, dict[str, tuple[float, float | None]]] = {}
    scope: str | None = None
    for page in pages:
        for line in page.splitlines():
            line = line.strip()
            heading = _SECTION.search(line)
            if heading:
                scope = heading.group(1)
                continue
            parsed = parse_row(line)
            if parsed is not None and scope is not None:
                name, value, pct = parsed
                result.setdefault(scope, {}).setdefault(name, (value, pct))
    return result


def check_month(pages: list[str], period: str) -> None:
    """Sanity-check an annexure against the month its link claims; raises DatasetError on a mismatch.

    The year must appear on the first page. If the page names any month in English (annexure IV's heading is
    scrambled by the PDF font and names none), the expected month must be among them.
    """
    year, month = period.split("-")
    first = pages[0] if pages else ""
    named = {number for number, name in MONTH_NAMES.items() if number and name in first}
    if year not in first or (named and int(month) not in named):
        raise DatasetError(f"AAI annexure for {period} does not match its link: header names {sorted(named)}")


def _whole(value: float | None) -> int | None:
    return None if value is None else int(round(value))


def combine(period: str, parsed: dict[int, dict[str, dict[str, tuple[float, float | None]]]]) -> list[dict]:
    """One traffic row per airport in the total tables (annexure II-IV part C), with the domestic and
    international splits where the A/B tables list the airport."""
    totals = {annex: parsed[annex].get(SCOPE_TOTAL, {}) for annex in ANNEXES}
    names = sorted(set().union(*(set(t) for t in totals.values())))
    rows = []
    for name in names:
        def value(annex: int, scope: str):
            entry = parsed[annex].get(scope, {}).get(name)
            return entry[0] if entry else None

        def change(annex: int):
            entry = totals[annex].get(name)
            return entry[1] if entry else None

        rows.append(
            {
                "airport_name": name,
                "iata_code": AAI_IATA.get(name),
                "period": period,
                "aircraft_movements": _whole(value(MOVEMENTS, SCOPE_TOTAL)),
                "passengers": _whole(value(PASSENGERS, SCOPE_TOTAL)),
                "freight_tonnes": value(FREIGHT, SCOPE_TOTAL),
                "movements_domestic": _whole(value(MOVEMENTS, SCOPE_DOMESTIC)),
                "movements_international": _whole(value(MOVEMENTS, SCOPE_INTERNATIONAL)),
                "passengers_domestic": _whole(value(PASSENGERS, SCOPE_DOMESTIC)),
                "passengers_international": _whole(value(PASSENGERS, SCOPE_INTERNATIONAL)),
                "freight_domestic_tonnes": value(FREIGHT, SCOPE_DOMESTIC),
                "freight_international_tonnes": value(FREIGHT, SCOPE_INTERNATIONAL),
                "movements_yoy_pct": change(MOVEMENTS),
                "passengers_yoy_pct": change(PASSENGERS),
                "freight_yoy_pct": change(FREIGHT),
            }
        )
    return rows


UPDATE_COLUMNS = [
    "iata_code", "icao_code", "aircraft_movements", "passengers", "freight_tonnes", "movements_domestic",
    "movements_international", "passengers_domestic", "passengers_international", "freight_domestic_tonnes",
    "freight_international_tonnes", "movements_yoy_pct", "passengers_yoy_pct", "freight_yoy_pct", "snapshot_id",
]


async def _icao_by_iata(db: AsyncSession) -> dict[str, str]:
    rows = (
        await db.execute(
            select(IndiaAirport.iata_code, IndiaAirport.icao_code).where(
                IndiaAirport.iata_code.is_not(None), IndiaAirport.icao_code.is_not(None)
            )
        )
    ).all()
    return {iata: icao for iata, icao in rows}


async def fetch_aai_traffic(
    db: AsyncSession, *, client: httpx.AsyncClient | None = None, base_dir: Path | str | None = None
) -> DatasetSnapshot:
    async def impl(snapshot: DatasetSnapshot) -> FetchOutcome:
        html = (await download(INDEX_URL, client=client)).decode("utf-8", errors="replace")
        reports = discover_reports(html)
        periods = latest_complete_periods(reports)
        if not periods:
            raise DatasetError("no month with annexures II, III and IV found on the AAI Traffic News page")
        icao = await _icao_by_iata(db)
        now = utcnow()
        rows: list[dict] = []
        digest = b""
        path = None
        for period in periods:
            parsed: dict[int, dict] = {}
            for annex in ANNEXES:
                content = await download(reports[period][annex], client=client)
                digest += content
                path = save_raw(SOURCE, f"{period}_annex{annex}.pdf", content, now=now, base=base_dir)
                try:
                    pages = await asyncio.to_thread(extract_pages, content)
                except Exception as exc:  # noqa: BLE001 - pdfminer raises many types on a bad PDF
                    raise DatasetError(f"AAI annexure {annex} for {period} is unreadable: {exc!r}") from exc
                check_month(pages, period)
                parsed[annex] = parse_annex(pages)
                if not parsed[annex].get(SCOPE_TOTAL):
                    raise DatasetError(f"AAI annexure {annex} for {period} has no airport rows")
            rows += combine(period, parsed)
        for row in rows:
            row["icao_code"] = icao.get(row["iata_code"]) if row["iata_code"] else None
            row["snapshot_id"] = snapshot.id
        await bulk_upsert(
            db, AirportTrafficMonthly, rows, conflict_columns=["airport_name", "period"], update_columns=UPDATE_COLUMNS
        )
        return FetchOutcome(
            row_count=len(rows),
            local_path=path,
            checksum=sha256_hex(digest),
            details={"periods": sorted(periods), "latest_period": periods[0], "airports": len({r["airport_name"] for r in rows})},
        )

    return await run_source(db, SOURCE, INDEX_URL, impl)
