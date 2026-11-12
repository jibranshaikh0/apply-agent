"""Comprehensive ATS form-label table: normalized label -> profile key.

mapping.py consults this table FIRST, before its pattern/fuzzy matching and
long before the OpenAI fallback. The table is generated systematically:
per-key base phrases (seeded from the MIT-licensed FormFilla dictionary,
github.com/AhmadHassan-BTed/FormFilla src/shared/dictionary/rules.json, plus
hand-collected variants of the standard Workday, Greenhouse, Ashby, Lever,
SmartRecruiters, Oracle/Taleo, iCIMS and Jibe application forms) crossed with
realistic phrasing patterns (question stems, "your" forms, region/tail
variants). Every generated entry is a plausible real form label.

Anything not in the table falls through to the existing code-pattern matcher
and then the OpenAI classifier. The table is the first pass, not a
replacement.
"""
from __future__ import annotations

from mapping import normalize

# ---------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------

# Question stems that produce distinct, plausible labels when crossed with
# yes/no question cores.
_YESNO_STEMS = [
    "do you",
    "are you",
    "will you",
    "would you",
    "have you",
    "can you",
]

# Tail variants common on Workday/Taleo/iCIMS legal-style questions.
_US_REGIONS = [
    "in the united states",
    "in the us",
    "in the u s",
    "in the usa",
    "in the u s a",
    "in the united states of america",
    "in the united states us",
]

# ---------------------------------------------------------------------------
# Explicit per-key variants (noun-style labels; these do not combinatorially
# explode, so they are listed by hand). All must be unique after normalize().
# ---------------------------------------------------------------------------

_EXPLICIT: dict[str, list[str]] = {
    "first_name": [
        "first name", "given name", "forename", "legal first name",
        "first/given name", "fname", "first", "christian name",
        "legal given name", "preferred first name", "what is first name",
        "what is legal first name", "enter first name", "applicant first name",
        "candidate first name", "first name (legal)", "first name(s)",
        "given name(s)", "first and middle name", "first name as per passport",
        "official first name", "primary first name", "first name of applicant",
        "please provide first name", "state first name", "indicate first name",
        "first name initial", "first and given name", "name - first",
        "first name text field", "legal first",
    ],
    "last_name": [
        "last name", "family name", "surname", "legal last name",
        "last/family name", "lname", "last", "last/family name (surname)",
        "legal family name", "what is last name", "enter last name",
        "applicant last name", "candidate last name", "last name (legal)",
        "last name(s)", "family name(s)", "surname(s)", "last name as per passport",
        "official last name", "primary last name", "last name of applicant",
        "please provide last name", "state last name", "indicate last name",
        "last and family name", "name - last", "last name text field",
        "legal last", "last surname", "second name",
    ],
    "middle_name": [
        "middle name", "middle initial", "middle name or initial",
        "legal middle name", "middle", "mid name", "second given name",
        "middle name(s)", "mi", "enter middle name", "middle names",
    ],
    "full_name": [
        "full name", "full legal name", "legal name", "name", "applicant name",
        "candidate name", "name of applicant", "what is name",
        "what is full name", "enter full name", "first and last name",
        "complete name", "entire name", "full name as per passport",
        "print name", "printed name", "name (first and last)",
        "name (last, first)", "last name, first name", "official name",
        "name of candidate", "please provide full name", "state full name",
        "type full name", "write full name", "contact name", "person name",
        "full name of applicant", "legal full name of applicant",
    ],
    "preferred_name": [
        "preferred name", "nickname", "preferred first name or nickname",
        "name you go by", "what should we call you", "what do you go by",
        "preferred", "goes by", "also known as", "aka", "chosen name",
        "preferred name or nickname", "display name", "common name",
        "name preferred", "what name do you prefer", "how should we address you",
        "name you prefer to be called", "preferred or chosen first name",
    ],
    "pronouns": [
        "pronouns", "preferred pronouns", "personal pronouns",
        "what are pronouns", "pronouns (optional)", "gender pronouns",
        "select pronouns", "choose pronouns", "pronouns i use",
        "my pronouns are", "which pronouns do you use",
        "what pronouns do you use", "pronouns you use", "pronoun",
    ],
    "email": [
        "email", "email address", "e-mail", "e-mail address", "email addr",
        "electronic mail", "contact email", "primary email",
        "what is email address", "what is email", "enter email address",
        "applicant email", "candidate email", "email address (primary)",
        "preferred email", "best email", "best email address",
        "email to contact you", "email where we can reach you",
        "personal email", "personal email address", "school email",
        "college email", "university email", "work email", "valid email",
        "valid email address", "active email address", "current email address",
        "re-enter email", "confirm email", "confirm email address",
        "retype email address", "verify email address", "repeat email",
        "email address confirmation", "type email address again",
        "email (required)", "mail id", "e mail id", "e-mail id",
    ],
    "phone": [
        "phone", "phone number", "mobile", "mobile number", "telephone",
        "telephone number", "cell", "cell phone", "cell phone number",
        "cellular", "cellular phone", "cellular number", "mobile phone",
        "mobile phone number", "contact number", "contact phone",
        "contact phone number", "primary phone", "primary phone number",
        "best number", "best number to reach you", "best phone number",
        "best phone number to reach you", "number to reach you",
        "number where we can reach you", "phone number to reach you",
        "what is phone number", "enter phone number", "applicant phone",
        "candidate phone number", "daytime phone", "daytime phone number",
        "evening phone", "home phone", "home phone number",
        "work phone", "work phone number", "phone (mobile)",
        "phone (cell)", "phone (home)", "phone (day)", "phone (evening)",
        "personal phone", "personal phone number", "current phone number",
        "valid phone number", "active phone number", "10 digit phone number",
        "phone no", "mobile no", "contact no", "phone num",
        "area code and phone number", "phone incl country code",
        "phone with country code", "full phone number",
    ],
    "address_line1": [
        "address", "street address", "address line 1", "address line one",
        "address 1", "street", "street line 1", "home address",
        "current address", "mailing address", "mailing address line 1",
        "residential address", "permanent address", "address (line 1)",
        "first line of address", "addr line 1", "address1", "street addr",
        "house number and street", "number and street",
    ],
    "address_line2": [
        "address line 2", "address line two", "address 2", "street line 2",
        "apartment", "apt", "apt/suite", "apartment or suite",
        "suite", "unit", "unit number", "apartment number",
        "mailing address line 2", "address (line 2)", "second line of address",
        "addr line 2", "address2", "apt suite unit",
    ],
    "location_city": [
        "city", "current city", "town", "city/town", "city or town",
        "city town", "what city", "enter city", "home city",
        "city of residence", "city of residence", "residence city",
        "mailing city", "address city", "city name", "city located",
        "in what city do you live", "which city do you live in",
        "city where you live", "city where you reside",
    ],
    "location_state": [
        "state", "current state", "province", "state/province",
        "state or province", "state province", "region", "state/region",
        "home state", "state of residence", "residence state",
        "mailing state", "address state", "what state", "enter state",
        "which state do you live in", "state where you live",
        "state where you reside", "us state", "u s state",
        "state abbreviation", "state code", "select state", "choose state",
    ],
    "location_zip": [
        "zip", "zip code", "zipcode", "postal code", "post code",
        "postcode", "zip/postal code", "zip or postal code",
        "postal/zip code", "zip postal code", "postal",
        "what is zip code", "enter zip code", "mailing zip",
        "address zip", "home zip code", "zip code of residence",
        "5 digit zip", "zip plus 4", "area postal code",
    ],
    "location_country": [
        "country", "country/region", "country or region", "country region",
        "country of residence", "residence country", "home country",
        "current country", "address country", "mailing country",
        "what country", "which country do you live in",
        "country where you live", "country where you reside",
        "country territory", "country/territory", "select country",
        "choose country", "country of citizenship residence",
        "country you live in", "country you reside in",
        "in which country do you currently reside",
        "in which country do you currently live",
        "country of current residence",
    ],
    "school": [
        "school", "university", "college", "institution", "school name",
        "university name", "college name", "name of school",
        "name of university", "name of college", "name of institution",
        "educational institution", "academic institution",
        "college or university", "college/university", "school or university",
        "what school do you attend", "what university do you attend",
        "what college do you attend", "which school do you attend",
        "which university do you attend", "which college do you attend",
        "where do you go to school", "where do you attend school",
        "what school", "which school", "enter school name",
        "current school", "current university", "current college",
        "most recent school", "most recent university", "most recent college",
        "last school attended", "last university attended",
        "school attended", "university attended", "college attended",
        "institution attended", "school you attend", "university you attend",
        "higher education institution", "post-secondary institution",
        "post secondary school", "undergraduate institution",
        "undergraduate university", "undergraduate school", "alma mater",
        "degree granting institution", "issuing institution",
        "academic institution name", "select school", "select university",
        "select college", "search for school", "search for university",
        "find school", "find university", "type of school name",
        "school (most recent)", "education institution",
    ],
    "degree": [
        "degree", "degree type", "highest degree", "degree level",
        "level of education", "education level", "highest level of education",
        "highest education level", "highest degree earned",
        "highest degree obtained", "highest degree completed",
        "highest level of education completed", "degree earned",
        "degree obtained", "degree completed", "degree pursued",
        "degree in progress", "degree sought", "current degree",
        "what degree", "which degree", "select degree", "choose degree",
        "degree program", "program of study level", "academic degree",
        "type of degree", "degree title", "degree name",
        "educational attainment", "highest qualification",
        "highest academic qualification", "qualification level",
        "what is highest level of education", "what degree are you pursuing",
        "what degree are you working towards", "what degree are you earning",
        "degree you are pursuing", "degree you are earning",
        "are you pursuing a degree", "degree (ba/bs/ms/phd)",
        "bachelors masters or phd", "ba bs ms or phd",
    ],
    "major": [
        "major", "field of study", "area of study", "concentration",
        "discipline", "major/concentration", "major or concentration",
        "field of study major", "academic major", "course of study",
        "program of study", "study program", "subject", "academic discipline",
        "specialization", "specialisation", "what is major",
        "what is field of study", "what do you study", "what are you studying",
        "what did you study", "enter major", "select major",
        "choose major", "primary major", "first major", "declared major",
        "intended major", "major field", "major subject", "study field",
        "field of concentration", "area of concentration",
        "main field of study", "primary field of study",
        "what was major", "undergraduate major", "college major",
        "university major", "degree major", "academic focus",
    ],
    "graduation_month": [
        "graduation month", "grad month", "month of graduation",
        "expected graduation month", "anticipated graduation month",
        "grad date month", "graduation date - month", "month of completion",
        "expected month of graduation", "when do you graduate - month",
        "graduation (month)", "completion month", "month of degree completion",
        "degree completion month", "education end month",
    ],
    "graduation_year": [
        "graduation year", "grad year", "year of graduation",
        "expected graduation year", "class year", "class of",
        "what year do you graduate", "when do you graduate",
        "when will you graduate", "when do you expect to graduate",
        "when do you anticipate graduating", "anticipated graduation year",
        "expected graduation date", "anticipated graduation date",
        "graduation date", "expected grad date", "grad date",
        "date of graduation", "expected date of graduation",
        "anticipated date of graduation", "year of completion",
        "expected year of graduation", "expected completion year",
        "degree completion year", "completion year", "education end year",
        "what is expected graduation date", "select graduation year",
        "expected graduation", "anticipated graduation",
        "estimated graduation date", "projected graduation date",
        "graduation timeframe", "when are you graduating",
        "what is graduation date", "graduating class of",
    ],
    "gpa": [
        "gpa", "grade point average", "cumulative gpa", "overall gpa",
        "current gpa", "major gpa", "gpa (4.0 scale)", "gpa on a 4.0 scale",
        "gpa (on a 4.0 scale)", "cumulative grade point average",
        "what is gpa", "what is current gpa", "enter gpa",
        "undergraduate gpa", "college gpa", "university gpa",
        "gpa out of 4.0", "gpa / 4.0", "grade average",
        "academic average", "cgpa", "cumulative grade average",
        "final gpa", "expected gpa", "in-major gpa", "major-specific gpa",
    ],
    "github": [
        "github", "github profile", "github url", "github link",
        "github profile url", "github username", "github account",
        "github page", "link to github", "link to github profile",
        "github.com profile", "what is github", "github handle",
        "github portfolio", "personal github",
    ],
    "linkedin": [
        "linkedin", "linkedin profile", "linkedin url", "linkedin link",
        "linkedin profile url", "linkedin page", "link to linkedin",
        "link to linkedin profile", "linkedin.com profile",
        "what is linkedin", "linkedin profile link", "linkedin address",
        "linkedin account", "linkedin username", "linkedin handle",
        "public linkedin url", "linkedin public profile",
    ],
    "portfolio": [
        "portfolio", "website", "personal website", "personal site",
        "portfolio url", "website url", "personal website url",
        "portfolio website", "portfolio link", "website link",
        "personal web site", "web site", "homepage", "personal homepage",
        "link to portfolio", "link to website", "online portfolio",
        "portfolio page", "personal page", "url of portfolio",
        "what is website", "portfolio or website", "website or portfolio",
        "personal url", "own website", "professional website",
        "personal web page", "portfolio address",
    ],
    "current_company": [
        "current company", "current employer", "company", "employer",
        "current organization", "current organisation", "company name",
        "employer name", "name of current employer", "name of employer",
        "where do you work", "where do you currently work",
        "what company do you work for", "present employer",
        "present company", "most recent company", "most recent employer",
        "latest employer", "company (current or most recent)",
        "current or most recent employer", "current or most recent company",
        "current place of work", "current workplace",
    ],
    "current_title": [
        "current title", "job title", "current job title", "title",
        "position", "current position", "position title", "role",
        "current role", "most recent title", "most recent position",
        "most recent job title", "what is job title",
        "what is current title", "what is current position",
        "professional title", "work title", "employment title",
        "title at current company", "position held", "latest job title",
    ],
    "resume_path": [
        "resume", "cv", "resume/cv", "cv/resume", "resume or cv",
        "upload resume", "attach resume", "resume file", "upload cv",
        "attach cv", "upload resume/cv", "attach resume/cv",
        "upload a resume", "upload resume", "resume upload",
        "drop resume here", "drag and drop resume", "resume attachment",
        "attach a resume", "attach resume file", "choose resume file",
        "select resume file", "browse resume", "add resume",
        "resume (pdf)", "resume (pdf or doc)", "upload resume pdf",
        "current resume", "updated resume", "latest resume",
        "curriculum vitae", "upload curriculum vitae",
        "please upload resume", "please attach resume",
        "resume document", "cv document", "resume or curriculum vitae",
    ],
    "cover_letter_path": [
        "cover letter", "upload cover letter", "attach cover letter",
        "cover letter file", "cover letter upload", "add cover letter",
        "attach a cover letter", "upload a cover letter",
        "cover letter attachment", "cover letter (optional)",
        "cover letter document", "select cover letter file",
        "cover letter pdf", "letter of interest", "motivation letter",
        "upload motivation letter", "cover note",
    ],
    "why_this_company": [
        "why do you want to work here", "why do you want to work for us",
        "why do you want this job", "why do you want this role",
        "why do you want this position", "why are you interested in this role",
        "why are you interested in this position",
        "why are you interested in this job",
        "why are you interested in working here",
        "why are you interested in working for us",
        "why are you interested in this company",
        "why are you interested in joining us",
        "why do you want to join us", "why do you want to join our team",
        "why do you want to work at this company",
        "why do you want to be a part of our team",
        "why this company", "why this role", "why this position",
        "what interests you about this role",
        "what interests you about this position",
        "what interests you about this job",
        "what interests you about working here",
        "what excites you about this role",
        "what excites you about this opportunity",
        "tell us why you want to work here",
        "tell us why you are interested in this position",
        "please describe why you are interested in this position",
        "briefly describe why you want to work here",
        "what makes you a good fit for this role",
        "why are you a good fit for this role",
        "why should we hire you", "why should we consider you",
        "what draws you to this company", "what draws you to this role",
    ],
    "skills": [
        "skills", "technical skills", "relevant skills", "key skills",
        "top skills", "list skills", "list relevant skills",
        "list technical skills", "what are skills", "what are top skills",
        "skills and qualifications", "qualifications", "areas of expertise",
        "expertise", "core competencies", "competencies",
        "professional skills", "skill set", "skillset", "abilities",
        "what skills do you have", "what skills do you possess",
        "describe skills", "enter skills", "add skills",
        "skills summary", "summary of skills", "programming languages",
        "technologies", "technologies you know", "tools and technologies",
        "what technologies are you proficient in",
    ],
}

# ---------------------------------------------------------------------------
# Combinatorial question families. Each family: stems x cores x tails, with
# skips for implausible combinations. All crossed entries must be plausible
# real ATS form labels.
# ---------------------------------------------------------------------------


def _cross(stems, cores, tails):
    out = []
    for s in stems:
        for c in cores:
            for t in tails:
                label = " ".join(p for p in (s, c, t) if p)
                out.append(label)
    return out


# -- work_authorization_us ---------------------------------------------------
_AUTH_STEMS = [
    "are you",
    "are you currently",
    "are you now",
    "do you confirm you are",
    "please confirm you are",
    "confirm that you are",
]
_AUTH_CORES = [
    "authorized to work",
    "legally authorized to work",
    "legally authorized to accept employment",
    "authorized to accept employment",
    "eligible to work",
    "legally eligible to work",
    "legally permitted to work",
    "permitted to work",
    "entitled to work",
    "legally entitled to work",
]
_AUTH_TAILS = _US_REGIONS + ["for this position", "in this country", ""]

work_authorization_labels = _cross(_AUTH_STEMS, _AUTH_CORES, _AUTH_TAILS) + [
    "work authorization", "work authorization status",
    "us work authorization", "u s work authorization",
    "united states work authorization", "work authorization (us)",
    "employment authorization", "employment eligibility",
    "employment eligibility verification", "right to work",
    "right to work in the united states", "proof of work authorization",
    "proof of eligibility to work", "work eligibility",
    "us work eligibility", "work permit status",
    "are you authorized to work for any employer in the united states",
    "are you authorized to work lawfully in the united states",
    "are you authorized to work in the country where this role is located",
    "are you authorized to work in the location of this job",
    "are you legally authorized to work for any employer in the us",
    "do you have authorization to work in the united states",
    "do you have the legal right to work in the united states",
    "do you have the right to work in the united states",
    "do you have work authorization for the united states",
    "i am authorized to work in the united states",
    "i am legally authorized to work in the united states",
    "are you eligible to accept employment in the united states",
    "are you eligible for employment in the united states without sponsorship",
    "are you currently authorized to work for any u s employer",
    "are you currently authorized to work for any united states employer",
    "select one: are you authorized to work in the united states",
    "are you able to work in the united states",
    "are you legally able to work in the united states",
    "can you provide proof of eligibility to work in the united states",
    "can you, after employment, submit verification of legal right to work in the united states",
    "if hired, can you provide proof of eligibility to work in the united states",
    "if hired, can you furnish proof of eligibility to work in the united states",
    "will you be able to provide verification of legal right to work in the united states",
]

# -- requires_sponsorship ----------------------------------------------------
_SPON_STEMS = [
    "do you",
    "will you",
    "do you now or in the future",
    "will you now or in the future",
    "will you now or at any point in the future",
    "do you now or at any point in the future",
    "will you at any point",
    "do you at any point",
    "will you in the future",
    "would you",
]
_SPON_CORES = [
    "require sponsorship",
    "require visa sponsorship",
    "require employment visa sponsorship",
    "require sponsorship for employment",
    "require sponsorship for employment visa status",
    "require sponsorship for an employment visa",
    "need sponsorship",
    "need visa sponsorship",
    "require immigration sponsorship",
    "require company sponsorship",
]
_SPON_TAILS = [
    "",
    "for employment",
    "in the united states",
    "in the us",
    "for employment in the united states",
    "to work in the united states",
    "to work in the us",
    "from the company",
    "for this role",
    "for this position",
]

requires_sponsorship_labels = _cross(_SPON_STEMS, _SPON_CORES, _SPON_TAILS) + [
    "visa sponsorship", "sponsorship", "sponsorship required",
    "requires sponsorship", "visa sponsorship required",
    "employment visa status", "visa status",
    "do you require sponsorship to work in this country",
    "do you require visa sponsorship to work in this country",
    "do you need sponsorship from the company now or in the future",
    "will you need visa sponsorship from us",
    "will you require sponsorship from the company",
    "are you on a visa that requires sponsorship",
    "do you currently hold a visa that requires employer sponsorship",
    "do you require immigration sponsorship now or in the future",
    "do you require visa sponsorship now or at any point in the future",
    "will you require visa sponsorship now or at any point in the future",
    "do you need immigration sponsorship now or at any point in the future",
    "do you now, or will you in the future, require sponsorship",
    "do you now or will you in the future require sponsorship for employment visa status",
    "will you now or in the future require sponsorship for employment visa status (e g h-1b visa status)",
    "will you now or in the future require sponsorship for employment visa status such as h-1b",
    "do you need the company to sponsor a work visa",
    "do you need an employer to sponsor work authorization",
    "will you need the company to commence (sponsor) an immigration case",
    "will you now or in the future require the company to commence (sponsor) an immigration case in order to employ you",
    "would you require visa sponsorship to work in the united states",
    "do you anticipate needing visa sponsorship",
    "do you foresee needing visa sponsorship",
    "do you expect to need sponsorship",
    "i will now or in the future require sponsorship",
    "sponsorship for work authorization",
    "sponsorship for employment authorization",
]

# -- us_citizen ----------------------------------------------------------------
us_citizen_labels = [
    "are you a u s citizen", "are you a us citizen",
    "are you a united states citizen", "are you a citizen of the united states",
    "u s citizen", "us citizen", "united states citizen",
    "citizenship", "citizenship status", "country of citizenship",
    "are you a citizen", "are you a us citizen or permanent resident",
    "are you a u s citizen or permanent resident",
    "are you a us citizen or green card holder",
    "are you a u s citizen or lawful permanent resident",
    "us citizenship", "u s citizenship",
    "are you a permanent resident", "are you a lawful permanent resident",
    "are you a green card holder", "do you hold a green card",
    "citizen or permanent resident", "nationality",
    "what is citizenship status", "what is citizenship",
    "select citizenship status", "indicate citizenship status",
    "are you a citizen or national of the united states",
    "are you a us person", "are you a u s person",
    "are you a protected individual under 8 u s c 1324b",
    "are you a us citizen, us national, lawful permanent resident, or asylee/refugee",
]

# -- willing_to_relocate -------------------------------------------------------
_RELOC_STEMS = ["are you", "would you be", "do you", "will you", "are you open to", "would you consider"]
_RELOC_CORES = [
    "willing to relocate",
    "willing to relocate for this role",
    "willing to relocate for this position",
    "willing to relocate for this job",
    "open to relocation",
    "open to relocating",
    "able to relocate",
    "prepared to relocate",
    "interested in relocating",
    "willing to move",
]
_RELOC_TAILS = [
    "",
    "if necessary",
    "if required",
    "for the right opportunity",
    "to the job location",
    "to the office location",
    "at own expense",
    "with relocation assistance",
]

willing_to_relocate_labels = _cross(_RELOC_STEMS, _RELOC_CORES, _RELOC_TAILS) + [
    "willing to relocate", "relocation", "relocation assistance",
    "relocation required", "relocation willingness", "open to relocation",
    "are you willing to relocate", "do you require relocation assistance",
    "will you need relocation assistance", "do you need relocation assistance",
    "would you need relocation assistance",
    "are you able to relocate to the job location",
    "are you willing to relocate to the office location",
    "are you willing to relocate if necessary",
    "are you willing to relocate at own expense",
    "do you plan to relocate", "are you planning to relocate",
    "are you local to this office", "are you local to this location",
    "are you currently located near this office",
    "this role is based in a specific location - are you able to work there",
    "are you able to work from the office location",
    "can you work on-site", "can you work onsite",
    "are you able to work on-site", "are you willing to work on-site",
    "are you comfortable with the location of this job",
    "are you comfortable commuting to this location",
    "are you comfortable commuting to the office",
    "are you comfortable working in an onsite setting",
]

# -- willing_to_travel ---------------------------------------------------------
_TRAVEL_STEMS = ["are you", "would you be", "do you", "can you"]
_TRAVEL_CORES = [
    "willing to travel",
    "able to travel",
    "open to travel",
    "comfortable with travel",
    "willing and able to travel",
]
_TRAVEL_TAILS = [
    "",
    "for work",
    "for business",
    "as required",
    "up to 25% of the time",
    "up to 50% of the time",
    "domestically",
    "internationally",
]

willing_to_travel_labels = _cross(_TRAVEL_STEMS, _TRAVEL_CORES, _TRAVEL_TAILS) + [
    "travel", "travel requirements", "willingness to travel",
    "ability to travel", "percentage of travel",
    "what percentage of time are you willing to travel",
    "how much travel are you comfortable with",
    "this role requires travel - are you comfortable with that",
]

# -- earliest_start_date -------------------------------------------------------
_START_STEMS = [
    "when can you start",
    "when could you start",
    "when would you be able to start",
    "when are you available to start",
    "when will you be available to start",
    "when can you begin",
    "when are you available to begin",
    "when will you be able to begin",
    "what is availability to start",
    "what is earliest start date",
    "what is available start date",
    "what is desired start date",
    "what date can you start",
    "what date are you available to start",
    "how soon can you start",
    "how soon could you start",
    "how soon are you available",
]
_START_BARE = [
    "start date", "earliest start date", "available start date",
    "desired start date", "preferred start date", "anticipated start date",
    "expected start date", "potential start date", "possible start date",
    "date available", "available date", "availability date",
    "date of availability", "availability to start", "availability",
    "when available", "date you can start", "date you could start",
    "proposed start date", "target start date", "ideal start date",
    "approximate start date", "estimated start date",
    "start date (if known)", "first available date",
    "available from", "available to start", "available to begin",
    "when available to start", "employment start date",
    "joining date", "date of joining", "possible joining date",
    "notice period", "current notice period", "length of notice period",
    "how much notice do you need to give",
    "what is notice period", "notice period at current employer",
]
earliest_start_date_labels = _START_STEMS + _START_BARE

# -- desired_salary ------------------------------------------------------------
_SAL_STEMS = [
    "what is",
    "what are",
    "please indicate",
    "please state",
    "please specify",
    "please provide",
    "indicate",
    "state",
    "specify",
    "enter",
]
_SAL_CORES = [
    "desired salary",
    "expected salary",
    "salary expectations",
    "salary expectation",
    "compensation expectations",
    "compensation expectation",
    "expected compensation",
    "desired compensation",
    "salary requirements",
    "salary requirement",
    "compensation requirements",
    "pay expectations",
    "expected pay",
    "desired pay",
    "target salary",
    "target compensation",
    "salary range expectations",
    "expected salary range",
    "desired salary range",
    "base salary expectations",
    "expected base salary",
    "annual salary expectations",
    "expected annual salary",
    "total compensation expectations",
]
_SAL_TAILS = ["", "for this role", "for this position", "for this job"]

desired_salary_labels = _cross(_SAL_STEMS, _SAL_CORES, _SAL_TAILS) + [
    "salary", "compensation", "pay", "salary range", "pay range",
    "compensation range", "desired salary", "expected salary",
    "salary expectations", "salary requirements", "compensation expectations",
    "what salary are you looking for", "what salary are you seeking",
    "what salary do you expect", "what compensation are you seeking",
    "what compensation do you expect", "what are salary requirements",
    "what are compensation expectations", "what are pay expectations",
    "how much do you expect to be paid", "what pay are you looking for",
    "desired annual salary", "expected annual compensation",
    "minimum salary", "minimum salary requirement",
    "minimum acceptable salary", "salary floor",
    "what is the minimum salary you would accept",
]

# -- referral_source -----------------------------------------------------------
_HEAR_STEMS = [
    "how did you hear about us",
    "how did you hear about this position",
    "how did you hear about this job",
    "how did you hear about this role",
    "how did you hear about this opportunity",
    "how did you hear about the position",
    "how did you hear about the job",
    "how did you hear about the opening",
    "how did you learn about us",
    "how did you learn about this position",
    "how did you learn about this job",
    "how did you learn about this role",
    "how did you learn about this opportunity",
    "how did you find out about us",
    "how did you find out about this position",
    "how did you find out about this job",
    "how did you find out about this role",
    "how did you find this position",
    "how did you find this job",
    "how did you find this role",
    "how did you come across this position",
    "how did you come across this job",
    "how did you come across this opportunity",
    "how did you discover this position",
    "how did you discover this job",
    "how did you discover us",
    "where did you hear about us",
    "where did you hear about this position",
    "where did you hear about this job",
    "where did you find this job",
    "where did you see this position",
    "where did you see this job posting",
    "where did you see this posting",
    "where did you see this job advertised",
    "how were you referred to us",
    "what led you to apply",
    "what brought you to this posting",
]
_HEAR_BARE = [
    "source", "referral source", "job source", "application source",
    "candidate source", "how heard", "how you heard about us",
    "hear about us", "heard about us", "source of application",
    "how you found us", "job board", "which job board",
    "select how you heard about us", "please select how you heard about us",
    "advertisement source", "recruiting source",
]
referral_source_labels = _HEAR_STEMS + _HEAR_BARE

# -- referred_by ---------------------------------------------------------------
referred_by_labels = [
    "referred by", "referral", "referral name", "name of referral",
    "were you referred", "were you referred by an employee",
    "were you referred by a current employee",
    "were you referred by someone at the company",
    "have you been referred", "have you been referred by an employee",
    "employee referral", "employee referral name",
    "name of employee who referred you",
    "if referred, by whom", "if you were referred, by whom",
    "who referred you", "who referred you to us",
    "referring employee", "referring employee name",
    "name of referring employee", "referrer", "referrer name",
    "referrer's name", "do you know anyone who works here",
    "do you know anyone at the company",
    "do you have any friends or family who work here",
    "do you have relatives employed by the company",
    "do you have any relatives working here",
    "are you related to anyone who works here",
]

# -- age_18_or_older -----------------------------------------------------------
age_18_or_older_labels = [
    "are you 18 or older", "are you 18 years or older",
    "are you 18 years of age or older", "are you at least 18",
    "are you at least 18 years old", "are you at least 18 years of age",
    "are you over 18", "are you over the age of 18",
    "are you age 18 or older", "are you aged 18 or older",
    "are you 18+", "are you eighteen or older",
    "are you older than 18", "are you of legal working age",
    "are you of legal age to work", "are you legally old enough to work",
    "18 years of age or older", "18 or older", "at least 18 years old",
    "are you at least 18 years of age or older",
    "i am 18 years of age or older", "i am at least 18 years old",
    "i certify that i am at least 18 years of age",
    "i certify that i am 18 years of age or older",
    "are you at least 21", "are you 21 or older",
    "are you at least 21 years of age",
]

# -- EEO: gender ----------------------------------------------------------------
eeoc_gender_labels = [
    "gender", "gender identity", "sex", "gender (optional)",
    "what is gender", "what is gender identity",
    "what gender do you identify as", "what gender do you identify with",
    "how do you identify", "how do you identify (gender)",
    "which gender do you identify as", "gender you identify with",
    "select gender", "choose gender", "please select gender",
    "gender identification", "gender designation",
    "do you identify as male or female",
    "what is sex", "sex (optional)", "sex at birth",
    "biological sex", "legal sex", "gender or sex",
    "voluntary self-identification of gender",
    "gender - voluntary self identification",
    "to which gender identity do you most identify",
    "which gender identity do you most identify with",
]

# -- EEO: race/ethnicity ---------------------------------------------------------
eeoc_race_labels = [
    "race", "ethnicity", "race/ethnicity", "race or ethnicity",
    "race and ethnicity", "racial identity", "ethnic background",
    "what is race", "what is ethnicity", "what is race or ethnicity",
    "what race do you identify as", "what ethnicity do you identify as",
    "select race", "choose race", "please select race",
    "select ethnicity", "choose ethnicity", "please select ethnicity",
    "race (optional)", "ethnicity (optional)",
    "voluntary self-identification of race",
    "race - voluntary self identification",
    "with which racial or ethnic group do you identify",
    "which of the following best describes racial or ethnic identity",
    "are you hispanic or latino", "are you of hispanic or latino origin",
    "hispanic or latino", "hispanic/latino", "are you hispanic/latino",
    "do you identify as hispanic or latino",
    "are you of hispanic, latino, or spanish origin",
    "what is racial or ethnic background",
    "what racial group do you identify with",
    "what ethnic group do you identify with",
    "please indicate race", "please indicate ethnicity",
    "please indicate race or ethnicity", "race/ethnic origin",
    "ethnic origin", "racial group", "ethnic group",
]

# -- EEO: veteran status ---------------------------------------------------------
_VET_STEMS = [
    "are you",
    "do you identify as",
    "have you served as",
    "do you consider yourself",
    "do you qualify as",
]
_VET_CORES = [
    "a veteran",
    "a protected veteran",
    "a disabled veteran",
    "a veteran of the us military",
    "a veteran of the u s armed forces",
    "an active duty service member",
    "an active duty wartime or campaign badge veteran",
    "a recently separated veteran",
    "an armed forces service medal veteran",
    "a member of the military",
    "a military veteran",
]
veteran_status_labels = _cross(_VET_STEMS, _VET_CORES, [""]) + [
    "veteran", "veteran status", "military status", "military service",
    "protected veteran", "protected veteran status",
    "voluntary self-identification of veteran status",
    "veteran status - voluntary self identification",
    "are you a veteran or active duty member of the military",
    "have you served in the military", "have you served in the armed forces",
    "have you ever served in the military",
    "have you ever served in the us armed forces",
    "have you ever served in the u s armed forces",
    "military veteran status", "military affiliation",
    "military experience", "do you have military experience",
    "veteran (optional)", "veteran status (optional)",
    "what is veteran status", "select veteran status",
    "please identify veteran status", "indicate veteran status",
    "what is military status", "are you currently in the military",
    "are you currently serving in the military",
    "are you a current or former member of the military",
    "are you a current or former member of the us armed forces",
]

# -- EEO: disability status ------------------------------------------------------
_DIS_STEMS = [
    "do you have",
    "are you",
    "do you identify as",
    "do you consider yourself",
    "have you",
    "are you someone with",
]
_DIS_CORES = [
    "a disability",
    "a physical or mental disability",
    "a disability or history of disability",
    "a disability or record of disability",
    "a physical or mental impairment",
    "a physical impairment",
    "a mental impairment",
    "a chronic medical condition",
    "a long-term health condition",
    "a sensory impairment",
    "a learning disability",
    "a visible or invisible disability",
]
disability_status_labels = _cross(_DIS_STEMS, _DIS_CORES, [""]) + [
    "disability", "disability status", "disabled",
    "voluntary self-identification of disability",
    "voluntary self identification of disability status",
    "disability status - voluntary self identification",
    "do you have a disability that requires accommodation",
    "do you require reasonable accommodation",
    "do you need reasonable accommodation",
    "do you need any accommodations",
    "do you require any accommodations",
    "will you need accommodation during the interview process",
    "do you need accommodations for the interview process",
    "do you need accommodations to perform this job",
    "do you require accommodations to perform the essential functions of this job",
    "are you able to perform the essential functions of this job",
    "are you able to perform the essential functions of this job with or without reasonable accommodation",
    "can you perform the essential functions of the job",
    "can you perform the essential functions of the position",
    "are you physically able to perform the duties of this position",
    "do you have any condition that would prevent you from performing the essential functions of this job",
    "form cc-305", "cc-305", "cc 305 voluntary self identification of disability",
    "what is disability status", "select disability status",
    "please identify disability status", "indicate disability status",
]

# ---------------------------------------------------------------------------
# Assemble the table. Duplicates within a key collapse; a label claimed by
# two different keys is a build error (caught by tests and at import).
# ---------------------------------------------------------------------------

_GENERATED: dict[str, list[str]] = {
    "work_authorization_us": work_authorization_labels,
    "requires_sponsorship": requires_sponsorship_labels,
    "us_citizen": us_citizen_labels,
    "willing_to_relocate": willing_to_relocate_labels,
    "willing_to_travel": willing_to_travel_labels,
    "earliest_start_date": earliest_start_date_labels,
    "desired_salary": desired_salary_labels,
    "referral_source": referral_source_labels,
    "referred_by": referred_by_labels,
    "age_18_or_older": age_18_or_older_labels,
    "eeoc_gender": eeoc_gender_labels,
    "eeoc_race": eeoc_race_labels,
    "eeoc_veteran_status": veteran_status_labels,
    "eeoc_disability_status": disability_status_labels,
}

# Canonical keys the table may map to: the canonical registry in mapping.py
# plus profile custom_answers keys.
CUSTOM_ANSWER_KEYS = {"why_this_company", "relocation_note", "skills"}


def build_label_table() -> dict[str, str]:
    """normalized label -> profile key. Raises on a cross-key collision."""
    table: dict[str, str] = {}
    raw_owner: dict[str, str] = {}
    for key, labels in list(_EXPLICIT.items()) + list(_GENERATED.items()):
        for raw in labels:
            n = normalize(raw)
            if not n:
                continue
            if n in table and table[n] != key:
                raise ValueError(
                    f"label collision: {raw!r} normalizes to {n!r}, "
                    f"claimed by both {table[n]!r} and {key!r}"
                )
            table[n] = key
            raw_owner.setdefault(n, raw)
    return table


LABEL_TABLE: dict[str, str] = build_label_table()
