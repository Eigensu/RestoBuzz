import re

class PhoneNormalizer:
    @staticmethod
    def normalize(raw_phone: str) -> str | None:
        """
        Normalizes phone numbers to canonical E.164-like format: +919876543210
        
        Rules:
        - remove spaces, hyphens, brackets
        - remove ".0" (Excel artifacts)
        - remove duplicate "+"
        - prepend "+" if missing
        - validate length (8-16 chars)
        """
        if not raw_phone:
            return None
            
        # Convert to string and handle Excel .0 artifact
        clean = str(raw_phone).replace(".0", "").strip()
        
        # Remove all non-digit characters except +
        clean = re.sub(r"[^0-9+]", "", clean)
        
        # Handle duplicate +
        clean = re.sub(r"\++", "+", clean)
        
        # Prepend + if missing
        if clean and not clean.startswith("+"):
            clean = "+" + clean
            
        # Validation
        if len(clean) < 8 or len(clean) > 17:
            return None
            
        return clean

phone_normalizer = PhoneNormalizer()
