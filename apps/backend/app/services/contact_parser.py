import csv
import io
import json
import uuid
from typing import BinaryIO
import phonenumbers
import openpyxl
from app.models.contact import ContactRow, InvalidRow, PreflightResult, ColumnMapping


def _normalize_phone(raw: str, default_region: str = "US") -> str | None:
    try:
        parsed = phonenumbers.parse(raw, default_region)
        if phonenumbers.is_valid_number(parsed):
            return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    except Exception:
        pass
    return None


def _parse_xlsx(content: bytes, mapping: ColumnMapping) -> tuple[list[dict], list[str]]:
    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return [], []
    headers = [str(h).strip() if h else "" for h in rows[0]]
    return [dict(zip(headers, row)) for row in rows[1:]], headers


def _parse_csv(content: bytes, mapping: ColumnMapping) -> tuple[list[dict], list[str]]:
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    headers = reader.fieldnames or []
    return rows, list(headers)


async def parse_contacts(
    content: bytes,
    filename: str,
    mapping: ColumnMapping,
    existing_phones: set[str],
) -> PreflightResult:
    if filename.endswith((".xlsx", ".xls")):
        raw_rows, headers = _parse_xlsx(content, mapping)
    else:
        raw_rows, headers = _parse_csv(content, mapping)

    valid: list[ContactRow] = []
    invalid: list[InvalidRow] = []
    seen_phones: set[str] = set()
    duplicate_count = 0
    suppressed_count = 0

    for i, row in enumerate(raw_rows, start=2):
        raw_phone = str(row.get(mapping.phone_column, "") or "").strip()
        if not raw_phone:
            invalid.append(InvalidRow(row_number=i, raw_phone="", reason="Empty phone"))
            continue

        normalized = _normalize_phone(raw_phone)
        if not normalized:
            invalid.append(InvalidRow(row_number=i, raw_phone=raw_phone, reason="Invalid phone number"))
            continue

        if normalized in seen_phones:
            duplicate_count += 1
            continue
        seen_phones.add(normalized)

        if normalized in existing_phones:
            suppressed_count += 1
            continue

        name = str(row.get(mapping.name_column or "", "") or "").strip()
        variables = {
            var: str(row.get(col, "") or "").strip()
            for var, col in mapping.variable_columns.items()
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
