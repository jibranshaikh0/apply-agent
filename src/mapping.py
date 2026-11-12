"""Form-label -> answer-key mapping, in code. No model calls in this file.

The agent collects form fields from the page; this module resolves each label
to a key of answers/profile.json deterministically. Only labels that fail
code mapping go to the model fallback in fill.py.
"""
from __future__ import annotations

import difflib
import re

# Canonical answer keys (must match answers/profile.json) -> known label aliases.
FIELD_ALIASES: dict[str, list[str]] = {
    "first_name": ["first name", "given name", "fname", "legal first name"],
    "last_name": ["last name", "surname", "family name", "lname", "legal last name"],
    "preferred_name": ["preferred name", "nickname", "preferred first name"],
    "email": ["email", "email address", "e-mail", "e-mail address"],
    "phone": ["phone", "phone number", "mobile", "mobile number", "telephone", "cell", "cell phone"],
    "location_city": ["city", "current city"],
    "location_state": ["state", "current state", "province"],
    "school": ["school", "university", "college", "institution", "school name", "university name"],
    "degree": ["degree", "degree type", "highest degree", "degree level"],
    "major": ["major", "field of study", "area of study", "concentration", "discipline"],
    "graduation_month": ["graduation month", "grad month"],
    "graduation_year": ["graduation year", "grad year", "year of graduation", "expected graduation year", "class year"],
    "gpa": ["gpa", "grade point average", "cumulative gpa"],
    "github": ["github", "github profile", "github url", "github link"],
    "linkedin": ["linkedin", "linkedin profile", "linkedin url", "linkedin link"],
    "portfolio": ["portfolio", "website", "personal website", "personal site", "portfolio url", "website url"],
    "work_authorization_us": [
        "are you authorized to work in the united states",
        "authorized to work in the us",
        "work authorization",
        "legally authorized to work",
        "are you legally authorized to work in the united states",
    ],
    "requires_sponsorship": [
        "will you now or in the future require sponsorship",
        "require sponsorship",
        "visa sponsorship",
        "do you require sponsorship",
        "will you require visa sponsorship",
    ],
    "willing_to_relocate": ["willing to relocate", "are you willing to relocate", "open to relocation"],
    "earliest_start_date": ["start date", "earliest start date", "available start date", "when can you start"],
    "resume_path": ["resume", "cv", "resume/cv", "upload resume", "attach resume", "resume file"],
    "middle_name": ["middle name", "middle initial"],
    "full_name": ["full name", "full legal name", "legal name"],
    "pronouns": ["pronouns", "preferred pronouns"],
    "address_line1": ["address", "street address", "address line 1"],
    "address_line2": ["address line 2", "apartment", "apt/suite"],
    "location_zip": ["zip", "zip code", "postal code"],
    "location_country": ["country", "country of residence"],
    "current_company": ["current company", "current employer"],
    "current_title": ["current title", "job title"],
    "us_citizen": ["are you a u s citizen", "us citizen", "citizenship status"],
    "desired_salary": ["desired salary", "salary expectations", "compensation expectations"],
    "referral_source": ["how did you hear about us", "source", "referral source"],
    "referred_by": ["referred by", "employee referral", "referral name"],
    "age_18_or_older": ["are you 18 or older", "are you at least 18"],
    "willing_to_travel": ["willing to travel", "are you willing to travel"],
    "eeoc_gender": ["gender", "gender identity"],
    "eeoc_race": ["race", "ethnicity", "race/ethnicity"],
    "eeoc_veteran_status": ["veteran status", "are you a veteran", "protected veteran"],
    "eeoc_disability_status": ["disability status", "do you have a disability"],
    "cover_letter_path": ["cover letter", "upload cover letter", "attach cover letter"],
}

_PUNCT = re.compile(r"[^a-z0-9 ]+")
_WS = re.compile(r"\s+")


def normalize(label: str) -> str:
    """Lowercase, strip punctuation and boilerplate, collapse whitespace."""
    s = label.lower()
    s = _PUNCT.sub(" ", s)
    s = _WS.sub(" ", s).strip()
    for filler in ("please enter your", "please provide your", "enter your", "your", "required", "optional"):
        s = s.replace(filler, " ")
    return _WS.sub(" ", s).strip()


# Precomputed normalized alias -> key lookup.
_ALIAS_INDEX: dict[str, str] = {
    normalize(alias): key for key, aliases in FIELD_ALIASES.items() for alias in aliases
}


def map_label(label: str, cutoff: float = 0.86) -> str | None:
    """Resolve a form label to a profile key, or None if unmapped."""
    n = normalize(label)
    if not n:
        return None
    # Pass 1: the comprehensive label table (src/label_table.py), pure code.
    from label_table import LABEL_TABLE
    if n in LABEL_TABLE:
        return LABEL_TABLE[n]
    if n in _ALIAS_INDEX:
        return _ALIAS_INDEX[n]
    # Containment: alias inside label or label inside alias.
    for alias, key in _ALIAS_INDEX.items():
        if len(alias) >= 4 and (alias in n or n in alias):
            return key
    # Fuzzy fallback, still pure code.
    close = difflib.get_close_matches(n, _ALIAS_INDEX.keys(), n=1, cutoff=cutoff)
    if close:
        return _ALIAS_INDEX[close[0]]
    return None
