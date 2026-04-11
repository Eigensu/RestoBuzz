import phonenumbers

def normalize_phone(raw: str, default_region: str = "IN") -> str | None:
    if raw is None:
        return None
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
    except (phonenumbers.NumberParseException, TypeError, ValueError):
        pass
    # Try prepending + if it looks like a full number without it
    if raw.isdigit() and len(raw) >= 10:
        try:
            parsed = phonenumbers.parse(f"+{raw}", None)
            if phonenumbers.is_valid_number(parsed):
                return phonenumbers.format_number(
                    parsed, phonenumbers.PhoneNumberFormat.E164
                )
        except (phonenumbers.NumberParseException, TypeError, ValueError):
            pass
    return None
