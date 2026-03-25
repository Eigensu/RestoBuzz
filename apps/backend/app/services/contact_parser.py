import csv
import io
import json
import uuid
import re
import phonenumbers
import openpyxl
from app.models.contact import ContactRow, InvalidRow, PreflightResult, ColumnMapping

# Common aliases for phone and name columns (lowercased, stripped)
_PHONE_ALIASES = {
    "phone",
    "contact",
    "mobile",
    "number",
    "tel",
    "telephone",
    "whatsapp",
    "wa",
    "cell",
    "phone number",
    "contact number",
    "mobile number",
}
_NAME_ALIASES = {
    "name",
    "full name",
    "fullname",
    "customer",
    "client",
    "person",
    "first name",
    "firstname",
    "contact name",
}


def _clean_header(h: str) -> str:
    """Lowercase, strip whitespace and trailing punctuation."""
    return re.sub(r"[:\-_]+$", "", str(h).strip().lower()).strip()


def _detect_columns(headers: list[str]) -> tuple[str | None, str | None]:
    """Return (phone_col, name_col) by matching against known aliases."""
    phone_col = name_col = None
    for raw in headers:
        cleaned = _clean_header(raw)
        if phone_col is None and cleaned in _PHONE_ALIASES:
            phone_col = raw
        if name_col is None and cleaned in _NAME_ALIASES:
            name_col = raw
    return phone_col, name_col


def _normalize_phone(raw: str, default_region: str = "IN") -> str | None:
    raw = str(raw).strip()
    # Strip common non-digit prefixes like leading apostrophe from Excel
    raw = raw.lstrip("'")
    try:
        parsed = phonenumbers.parse(raw, default_region)
        if phonenumbers.is_valid_number(parsed):
            return phonenumbers.format_number(
                parsed, phonenumbers.PhoneNumberFormat.E164
            )
    except Exception:
        pass
    # Try prepending + if it looks like a full number without it
    if raw.isdigit() and len(raw) >= 10:
        try:
            parsed = phonenumbers.parse(f"+{raw}", None)
            if phonenumbers.is_valid_number(parsed):
                return phonenumbers.format_number(
                    parsed, phonenumbers.PhoneNumberFormat.E164
                )
        except Exception:
            pass
    return None


def _parse_xlsx(content: bytes) -> tuple[list[dict], list[str]]:
    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return [], []
    headers = [str(h).strip() if h is not None else "" for h in rows[0]]
    return [dict(zip(headers, row)) for row in rows[1:]], headers


def _parse_csv(content: bytes) -> tuple[list[dict], list[str]]:
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    headers = list(reader.fieldnames or [])
    return rows, headers


async def parse_contacts(
    content: bytes,
    filename: str,
    mapping: ColumnMapping,
    existing_phones: set[str],
) -> PreflightResult:
    if filename.lower().endswith((".xlsx", ".xls")):
        raw_rows, headers = _parse_xlsx(content)
    else:
        raw_rows, headers = _parse_csv(content)

    # Auto-detect columns if the provided mapping columns aren't found in headers
    header_set = set(headers)
    phone_col = mapping.phone_column if mapping.phone_column in header_set else None
    name_col = mapping.name_column if mapping.name_column in header_set else None

    if phone_col is None or name_col is None:
        detected_phone, detected_name = _detect_columns(headers)
        if phone_col is None:
            phone_col = detected_phone
        if name_col is None:
            name_col = detected_name

    if phone_col is None:
        # Last resort: try every column for phone-like values
        for h in headers:
            if any(
                alias in _clean_header(h)
                for alias in ("phone", "contact", "mobile", "number")
            ):
                phone_col = h
                break

    valid: list[ContactRow] = []
    invalid: list[InvalidRow] = []
    seen_phones: set[str] = set()
    duplicate_count = 0
    suppressed_count = 0

    for i, row in enumerate(raw_rows, start=2):
        raw_phone = str(row.get(phone_col, "") or "").strip() if phone_col else ""
        if not raw_phone or raw_phone.lower() in ("none", "null", "n/a", "-"):
            invalid.append(InvalidRow(row_number=i, raw_phone="", reason="Empty phone"))
            continue

        normalized = _normalize_phone(raw_phone)
        if not normalized:
            invalid.append(
                InvalidRow(
                    row_number=i, raw_phone=raw_phone, reason="Invalid phone number"
                )
            )
            continue

        if normalized in seen_phones:
            duplicate_count += 1
            continue
        seen_phones.add(normalized)

        if normalized in existing_phones:
            suppressed_count += 1
            continue

        name = str(row.get(name_col, "") or "").strip() if name_col else ""
        variables = {
            var: str(row.get(col, "") or "").strip()
            for var, col in (mapping.variable_columns or {}).items()
        }

        valid.append(ContactRow(name=name, phone=normalized, variables=variables))

    file_ref = str(uuid.uuid4())
    return PreflightResult(
        valid_count=len(valid),
        invalid_count=len(invalid),
        duplicate_count=duplicate_count,
        suppressed_count=suppressed_count,
        valid_rows=valid,
        invalid_rows=invalid,
        file_ref=file_ref,
    )
