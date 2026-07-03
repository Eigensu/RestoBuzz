import phonenumbers

# Default region used to resolve bare national numbers. Contacts are uploaded as
# Excel sheets that frequently contain 10-digit Indian mobiles with no country
# code; without a default region those normalize to a bogus "+<digits>" (e.g.
# 7977539750 -> +7977539750, which is not India). Numbers that already carry a
# country code — a leading "+" or a recognizable CC prefix like 91 — are
# respected, so genuine international numbers are preserved.
DEFAULT_REGION = "IN"


def normalize_phone(raw_phone: str, region: str = DEFAULT_REGION) -> str | None:
    """Normalize a phone number to E.164 (e.g. +919876543210).

    Uses libphonenumber so a bare national number gets the correct country code
    for `region`, while numbers with an explicit country code (leading "+", or a
    CC prefix such as 91 that libphonenumber recognizes for the region) are kept
    as-is. Returns None if the input can't be parsed or isn't a valid, dialable
    number — invalid rows are surfaced in campaign preflight rather than sent.
    """
    if not raw_phone:
        return None

    # Excel stores phone cells as floats -> ".0" artifact; drop it before parsing.
    clean = str(raw_phone).replace(".0", "").strip()
    if not clean:
        return None

    try:
        parsed = phonenumbers.parse(clean, region)
    except phonenumbers.NumberParseException:
        return None

    if not phonenumbers.is_valid_number(parsed):
        return None

    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
