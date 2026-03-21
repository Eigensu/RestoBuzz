from pydantic import BaseModel


class ContactRow(BaseModel):
    name: str
    phone: str  # E.164 normalized
    variables: dict[str, str] = {}


class InvalidRow(BaseModel):
    row_number: int
    raw_phone: str
    reason: str


class PreflightResult(BaseModel):
    valid_count: int
    invalid_count: int
    duplicate_count: int
    suppressed_count: int
    valid_rows: list[ContactRow]
    invalid_rows: list[InvalidRow]
    file_ref: str  # Redis key for cached valid rows


class ColumnMapping(BaseModel):
    phone_column: str
    name_column: str | None = None
    variable_columns: dict[str, str] = {}  # template_var -> column_name
