from pydantic import BaseModel, Field


class ContactRow(BaseModel):
    name: str | None = None
    phone: str | None = None  # E.164 normalized
    email: str | None = None
    variables: dict[str, str] = Field(default_factory=dict)


class InvalidRow(BaseModel):
    row_number: int
    raw_value: str
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
    phone_column: str | None = None
    email_column: str | None = None
    name_column: str | None = None
    variable_columns: dict[str, str] = Field(
        default_factory=dict
    )  # template_var -> column_name
