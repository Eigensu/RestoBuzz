import csv
import io
import json
import uuid
import re
import phonenumbers
import openpyxl
from app.models.contact import ContactRow, InvalidRow, PreflightResult, ColumnMapping
from app.core.logging import get_logger

logger = get_logger(__name__)

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


_EMAIL_ALIASES = {
    "email",
    "mail",
    "e-mail",
    "email address",
    "emailaddress",
    "address",
}
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


def _detect_columns(headers: list[str]) -> tuple[str | None, str | None, str | None]:
    """Return (phone_col, email_col, name_col) by matching against known aliases."""
    phone_col = email_col = name_col = None
    for raw in headers:
        cleaned = _clean_header(raw)
        if phone_col is None and cleaned in _PHONE_ALIASES:
            phone_col = raw
        if email_col is None and cleaned in _EMAIL_ALIASES:
            email_col = raw
        if name_col is None and cleaned in _NAME_ALIASES:
            name_col = raw
    return phone_col, email_col, name_col


def _normalize_phone(raw: str, default_region: str = "IN") -> str | None:
    raw = str(raw).strip()
    # Strip common non-digit prefixes like leading apostrophe from Excel
    raw = raw.lstrip("'")
    # Excel stores numeric cells as floats — strip trailing .0
    if raw.endswith(".0") and raw[:-2].isdigit():
        raw = raw[:-2]
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


def _validate_email(raw: str) -> str | None:
    raw = str(raw).strip().lower()
    if not raw:
        return None
    # Very basic regex for email validation
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    if re.match(pattern, raw):
        return raw
    return None


def _parse_xlsx(content: bytes) -> tuple[list[dict], list[str]]:
    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return [], []
    headers = [str(h).strip() if h is not None else "" for h in rows[0]]

    def _cell(v: object) -> str:
        if v is None:
            return ""
        # openpyxl returns numeric phone cells as float — convert cleanly
        if isinstance(v, float) and v == int(v):
            return str(int(v))
        return str(v).strip()

    return [dict(zip(headers, [_cell(c) for c in row])) for row in rows[1:]], headers


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

    # Auto-detect columns
    header_set = set(headers)
    phone_col = mapping.phone_column if mapping.phone_column in header_set else None
    email_col = mapping.email_column if mapping.email_column in header_set else None
    name_col = mapping.name_column if mapping.name_column in header_set else None

    # Restore Auto-Detection if not provided
    if phone_col is None or email_col is None or name_col is None:
        det_phone, det_email, det_name = _detect_columns(headers)
        if phone_col is None: phone_col = det_phone
        if email_col is None: email_col = det_email
        if name_col is None: name_col = det_name

    logger.info(
        "contact_parser_columns_detected",
        phone_col=phone_col,
        email_col=email_col,
        name_col=name_col,
        all_headers=headers
    )
    print(f"🔎 MAPPED COLUMNS -> Phone: [{phone_col}], Email: [{email_col}], Name: [{name_col}]")

    valid: list[ContactRow] = []
    invalid: list[InvalidRow] = []
    seen_identifiers: set[str] = set()  # Can be phone or email
    duplicate_count = 0
    suppressed_count = 0

    for i, row in enumerate(raw_rows, start=2):
        raw_phone = str(row.get(phone_col, "") or "").strip() if phone_col else ""
        raw_email = str(row.get(email_col, "") or "").strip() if email_col else ""
        
        normalized_phone = _normalize_phone(raw_phone) if raw_phone else None
        normalized_email = _validate_email(raw_email) if raw_email else None

        if i < 10: # Print first 10 rows
            print(f"📍 ROW {i} -> Raw Email: '{raw_email}' | Parsed: '{normalized_email}'")
            logger.info(
                "contact_parser_row_debug",
                row=i,
                raw_phone=raw_phone,
                norm_phone=normalized_phone,
                raw_email=raw_email,
                norm_email=normalized_email
            )

        # Row is invalid if both are missing or syntactically wrong
        if not normalized_phone and not normalized_email:
            reason = "Missing or invalid phone and email"
            if raw_phone and not normalized_phone: reason = f"Invalid phone: {raw_phone}"
            elif raw_email and not normalized_email: reason = f"Invalid email: {raw_email}"
            
            invalid.append(InvalidRow(row_number=i, raw_value=raw_phone or raw_email or "EMPTY", reason=reason))
            continue

        # Check duplicates (prefer phone for uniqueness if both present, else email)
        identifier = normalized_phone or normalized_email
        if identifier in seen_identifiers:
            duplicate_count += 1
            continue
        seen_identifiers.add(identifier)

        # Suppression check
        if normalized_phone and normalized_phone in existing_phones:
            suppressed_count += 1
            continue

        name = str(row.get(name_col, "") or "").strip() if name_col else ""
        variables = {
            var: str(row.get(col, "") or "").strip()
            for var, col in (mapping.variable_columns or {}).items()
        }

        # Row must have 'email' key at top level for the Email Campaign validator
        valid.append(ContactRow(
            name=name, 
            phone=normalized_phone, 
            email=normalized_email,
            variables=row
        ))

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
