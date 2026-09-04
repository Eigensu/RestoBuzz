from pydantic import BaseModel, Field


class ContactRow(BaseModel):
    name: str | None = None
    phone: str | None = None  # E.164 normalized
    email: str | None = None
    variables: dict[str, str] = Field(default_factory=dict)
    # Every non-empty cell of the source row, keyed by column header. Template
    # variables are mapped to columns in the campaign wizard, which runs after
    # the upload — without the raw row the sheet would have to be uploaded
    # again just to change a mapping.
    row: dict[str, str] = Field(default_factory=dict)


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
    # Column headers as they appear in the sheet, so the wizard can offer them
    # as sources for the template's variables.
    headers: list[str] = Field(default_factory=list)


class ColumnMapping(BaseModel):
    phone_column: str | None = None
    email_column: str | None = None
    name_column: str | None = None
    variable_columns: dict[str, str] = Field(
        default_factory=dict
    )  # template_var -> column_name
