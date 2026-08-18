"""Normalization engine.

Converts heterogeneous source representations into one canonical internal structure:
titles, company names, locations, employment types, experience levels, salaries and dates.

Pure functions only — trivially unit-testable and reusable by any connector.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Iterable, NamedTuple

from pakjobs_core.domain.enums import EmploymentType, ExperienceLevel, WorkMode
from pakjobs_core.domain.locations import (
    CITY_LOOKUP,
    COUNTRY_ALIASES,
    PROVINCE_ALIASES,
    City,
)
from pakjobs_core.pipeline.text import collapse_whitespace, normalize_text, slugify

# ---------------------------------------------------------------------------
# Titles
# ---------------------------------------------------------------------------

_TITLE_NOISE = [
    re.compile(r"\((?:urgent|hiring|apply now|immediate joining|new)\)", re.IGNORECASE),
    re.compile(r"\b(?:urgent(?:ly)? required|apply now|hiring now|we are hiring|job opening[s]?)\b[:\-–—]?", re.IGNORECASE),
    # Leading marketing prefix: "URGENT:", "Hiring -", "Vacancy —", "Job Opening:"
    re.compile(
        r"^\s*(?:urgent|hiring|vacancy|job|position|opening|required|wanted|new)\s*[:\-–—]\s*",
        re.IGNORECASE,
    ),
    re.compile(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]"),  # emoji
    re.compile(r"^\s*(?:re|fwd)\s*:\s*", re.IGNORECASE),
]
_TITLE_TRAILING_LOCATION = re.compile(
    r"\s*[-–—|,]\s*(?:based in\s+)?(?:%s)\s*(?:,\s*pakistan)?\s*$"
    % "|".join(sorted({re.escape(k) for k in CITY_LOOKUP}, key=len, reverse=True)),
    re.IGNORECASE,
)
_TITLE_TRAILING_COUNTRY = re.compile(r"\s*[-–—|,]\s*pakistan\s*$", re.IGNORECASE)
_TITLE_SEPARATORS = re.compile(r"\s*[|/]\s*")

_ACRONYMS = {"qa", "ui", "ux", "it", "hr", "ai", "ml", "seo", "sre", "api", "erp", "crm", "php", "sql", "aws", "gcp"}


def normalize_title(raw: str | None) -> str:
    """Clean a job title: strip marketing noise, trailing location and stray separators."""
    if not raw:
        return ""
    title = collapse_whitespace(raw)
    for pattern in _TITLE_NOISE:
        title = pattern.sub(" ", title)
    title = collapse_whitespace(title)
    title = _TITLE_TRAILING_LOCATION.sub("", title)
    title = _TITLE_TRAILING_COUNTRY.sub("", title)
    title = _TITLE_SEPARATORS.sub(" - ", title)
    title = title.strip(" -–—|,:;")
    title = collapse_whitespace(title)
    if title.isupper() and len(title) > 6:
        title = _titlecase(title)
    return title[:400]


def _titlecase(value: str) -> str:
    words = []
    for word in value.split():
        low = word.lower()
        words.append(word.upper() if low.strip("().,") in _ACRONYMS else low.capitalize())
    return " ".join(words)


def title_comparison_key(title: str) -> str:
    """Aggressively reduced title used for duplicate matching (seniority-insensitive core)."""
    text = normalize_text(title)
    text = re.sub(r"\b(sr|snr|senior|jr|junior|lead|principal|staff|associate|assistant)\b", " ", text)
    text = re.sub(r"\b(i{1,3}|iv|v|1|2|3|4|5)\b\s*$", " ", text)
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    return collapse_whitespace(text)


# ---------------------------------------------------------------------------
# Company names
# ---------------------------------------------------------------------------

_COMPANY_SUFFIXES = [
    "private limited", "pvt limited", "pvt ltd", "pvt. ltd.", "pvt", "private",
    "limited", "ltd", "llc", "l.l.c", "inc", "incorporated", "corporation", "corp",
    "company", "co", "gmbh", "plc", "sarl", "bv", "ag", "sa", "spa", "pty",
    "technologies", "technology", "tech", "solutions", "systems", "services",
    "software", "labs", "group", "holdings", "international", "global", "enterprises",
    "consultancy", "consulting", "industries", "ventures", "partners", "associates",
]
_SUFFIX_RE = re.compile(
    r"\b(?:%s)\b\.?\s*$" % "|".join(re.escape(s) for s in sorted(_COMPANY_SUFFIXES, key=len, reverse=True)),
    re.IGNORECASE,
)
_COMPANY_PAREN = re.compile(r"\s*\([^)]*\)\s*")


def normalize_company_name(raw: str | None) -> str:
    """Display form of a company name (whitespace + punctuation tidy)."""
    if not raw:
        return ""
    name = collapse_whitespace(raw)
    name = name.strip(" .,-–—|")
    return name[:240]


def company_matching_key(raw: str | None) -> str:
    """Canonical key that merges 'ABC', 'ABC Technologies' and 'ABC (Pvt) Ltd'."""
    if not raw:
        return ""
    name = normalize_text(raw)
    name = _COMPANY_PAREN.sub(" ", name)
    name = re.sub(r"[^a-z0-9& ]+", " ", name)
    name = collapse_whitespace(name)
    # Strip repeated trailing corporate suffixes ("abc technologies pvt ltd" -> "abc").
    # Keep the last non-empty form: a company literally named "Systems Limited" must not
    # reduce to an empty string just because every token is also a generic suffix.
    previous = None
    while previous != name:
        previous = name
        stripped = collapse_whitespace(_SUFFIX_RE.sub("", name))
        if not stripped:
            break
        name = stripped
    return name or normalize_text(raw)


# ---------------------------------------------------------------------------
# Locations
# ---------------------------------------------------------------------------


class NormalizedLocation(NamedTuple):
    location: str | None
    city: str | None
    city_slug: str | None
    province: str | None
    country: str
    is_remote: bool
    work_mode: str


_REMOTE_RE = re.compile(r"\b(remote|work from home|wfh|anywhere|telecommute|distributed)\b", re.IGNORECASE)
_HYBRID_RE = re.compile(r"\bhybrid\b", re.IGNORECASE)
_ONSITE_RE = re.compile(r"\b(on[- ]?site|in[- ]?office|in[- ]?person)\b", re.IGNORECASE)
_SPLIT_RE = re.compile(r"\s*[,/|;\-–—]\s*|\s+in\s+|\s+at\s+", re.IGNORECASE)


def normalize_location(raw: str | None, *, extra_text: str | None = None, default_country: str = "PK") -> NormalizedLocation:
    """Parse arbitrary location strings into city/province/country + work mode.

    Handles 'Lahore, Pakistan', 'Software Engineer - Lahore', 'Remote (Pakistan)',
    'Karachi / Islamabad', 'Punjab, PK', 'Hybrid — Lahore'.
    """
    raw_text = collapse_whitespace(raw or "")
    haystack = f"{raw_text} {extra_text or ''}"

    is_remote = bool(_REMOTE_RE.search(haystack))
    is_hybrid = bool(_HYBRID_RE.search(haystack))
    is_onsite = bool(_ONSITE_RE.search(haystack))

    city: City | None = None
    province: str | None = None
    country: str | None = None

    tokens = [t for t in _SPLIT_RE.split(raw_text) if t]
    # Whole-string match first (handles multi-word cities such as "Rahim Yar Khan")
    candidates = [raw_text, *tokens]
    for token in candidates:
        key = normalize_text(token)
        if not key:
            continue
        if city is None and key in CITY_LOOKUP:
            city = CITY_LOOKUP[key]
        if province is None and key in PROVINCE_ALIASES:
            province = PROVINCE_ALIASES[key]
        if country is None and key in COUNTRY_ALIASES:
            country = COUNTRY_ALIASES[key]

    # Substring scan as a fallback ("Software Engineer - Lahore Office")
    if city is None and raw_text:
        low = normalize_text(raw_text)
        for name, candidate in CITY_LOOKUP.items():
            if len(name) < 4:
                continue
            if re.search(rf"\b{re.escape(name)}\b", low):
                city = candidate
                break

    if city and not province:
        province = city.province
    if city or province:
        country = country or "PK"

    if is_remote and not is_hybrid:
        work_mode = WorkMode.REMOTE
    elif is_hybrid:
        work_mode = WorkMode.HYBRID
    elif is_onsite or city:
        work_mode = WorkMode.ONSITE
    else:
        work_mode = WorkMode.UNKNOWN

    display = _build_display_location(raw_text, city, province, is_remote)
    return NormalizedLocation(
        location=display,
        city=city.name if city else None,
        city_slug=city.slug if city else None,
        province=province,
        country=country or default_country,
        is_remote=work_mode == WorkMode.REMOTE,
        work_mode=work_mode,
    )


def _build_display_location(raw: str, city: City | None, province: str | None, is_remote: bool) -> str | None:
    if city:
        return f"{city.name}, {city.province}"
    if province:
        return province
    if is_remote:
        return "Remote"
    return raw or None


# ---------------------------------------------------------------------------
# Employment type
# ---------------------------------------------------------------------------

_EMPLOYMENT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bintern(ship)?s?\b|\btrainee\b|\bapprentice", re.IGNORECASE), EmploymentType.INTERNSHIP),
    (re.compile(r"\bpart[\s\-_]?time\b|\bparttime\b", re.IGNORECASE), EmploymentType.PART_TIME),
    (re.compile(r"\bcontract(ual|or)?\b|\bfixed[\s\-]term\b|\bb2b\b", re.IGNORECASE), EmploymentType.CONTRACT),
    (re.compile(r"\btemporary\b|\bseasonal\b|\bcasual\b", re.IGNORECASE), EmploymentType.TEMPORARY),
    (re.compile(r"\bfreelance\b|\bconsultant\b|\bgig\b", re.IGNORECASE), EmploymentType.FREELANCE),
    (re.compile(r"\bvolunteer\b|\bunpaid\b", re.IGNORECASE), EmploymentType.VOLUNTEER),
    (re.compile(r"\bfull[\s\-_]?time\b|\bfulltime\b|\bpermanent\b|\bregular\b", re.IGNORECASE), EmploymentType.FULL_TIME),
]


def normalize_employment_type(*values: str | None) -> str:
    """First matching signal wins; internship beats full-time when both appear."""
    haystack = " ".join(v for v in values if v)
    if not haystack.strip():
        return EmploymentType.UNKNOWN
    for pattern, value in _EMPLOYMENT_PATTERNS:
        if pattern.search(haystack):
            return value
    return EmploymentType.UNKNOWN


# ---------------------------------------------------------------------------
# Experience
# ---------------------------------------------------------------------------

_YEARS_RE = re.compile(
    r"(\d{1,2})\s*(?:\+|plus)?\s*(?:-|to|–)?\s*(\d{1,2})?\s*(?:\+)?\s*(?:years?|yrs?)\b(?:[^.]{0,30}?experience)?",
    re.IGNORECASE,
)
_EXPERIENCE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bintern(ship)?\b|\btrainee\b", re.IGNORECASE), ExperienceLevel.INTERN),
    (re.compile(r"\bfresh(er|ies)?\b|\bfresh graduate\b|\bno experience\b|\bgraduate (program|trainee|scheme)\b", re.IGNORECASE), ExperienceLevel.FRESH_GRADUATE),
    (re.compile(r"\b(c[\-\s]?level|chief|vp|vice president|head of|director)\b", re.IGNORECASE), ExperienceLevel.EXECUTIVE),
    (re.compile(r"\b(principal|staff engineer|lead|team lead|tech lead|manager)\b", re.IGNORECASE), ExperienceLevel.LEAD),
    (re.compile(r"\b(sr\.?|snr|senior|expert|specialist iii)\b", re.IGNORECASE), ExperienceLevel.SENIOR),
    (re.compile(r"\b(jr\.?|junior|entry[\s\-]level|associate)\b", re.IGNORECASE), ExperienceLevel.ENTRY),
    (re.compile(r"\bmid[\s\-]?(level|senior)?\b|\bintermediate\b", re.IGNORECASE), ExperienceLevel.MID),
]


def extract_years_of_experience(text: str | None) -> tuple[int | None, int | None]:
    if not text:
        return None, None
    match = _YEARS_RE.search(text)
    if not match:
        return None, None
    low = int(match.group(1))
    high = int(match.group(2)) if match.group(2) else None
    if high is not None and high < low:
        low, high = high, low
    if low > 40:
        return None, None
    return low, high


def normalize_experience_level(title: str | None, description: str | None = None, explicit: str | None = None) -> str:
    """Title and explicit field dominate; description years act as a tie-breaker."""
    if explicit:
        for pattern, value in _EXPERIENCE_PATTERNS:
            if pattern.search(explicit):
                return value
    for pattern, value in _EXPERIENCE_PATTERNS:
        if title and pattern.search(title):
            return value

    low, _ = extract_years_of_experience(description)
    if low is not None:
        if low == 0:
            return ExperienceLevel.FRESH_GRADUATE
        if low <= 1:
            return ExperienceLevel.ENTRY
        if low <= 4:
            return ExperienceLevel.MID
        if low <= 8:
            return ExperienceLevel.SENIOR
        return ExperienceLevel.LEAD

    if description:
        for pattern, value in _EXPERIENCE_PATTERNS:
            if pattern.search(description[:1500]):
                return value
    return ExperienceLevel.UNKNOWN


# ---------------------------------------------------------------------------
# Salary
# ---------------------------------------------------------------------------


class NormalizedSalary(NamedTuple):
    min_amount: Decimal | None
    max_amount: Decimal | None
    currency: str | None
    period: str | None


_CURRENCY_MAP = {
    "pkr": "PKR", "rs": "PKR", "rs.": "PKR", "rupees": "PKR", "rupee": "PKR", "₨": "PKR", "pk rs": "PKR",
    "usd": "USD", "$": "USD", "us$": "USD", "dollars": "USD",
    "gbp": "GBP", "£": "GBP", "eur": "EUR", "€": "EUR", "aed": "AED", "sar": "SAR",
}
_PERIOD_MAP = [
    (re.compile(r"\b(per\s+)?(month|monthly|/\s*mo|p\.?m\.?)\b", re.IGNORECASE), "month"),
    (re.compile(r"\b(per\s+)?(year|annum|yearly|annually|/\s*yr|p\.?a\.?)\b", re.IGNORECASE), "year"),
    (re.compile(r"\b(per\s+)?(hour|hourly|/\s*hr)\b", re.IGNORECASE), "hour"),
    (re.compile(r"\b(per\s+)?(week|weekly)\b", re.IGNORECASE), "week"),
    (re.compile(r"\b(per\s+)?(day|daily)\b", re.IGNORECASE), "day"),
]
_AMOUNT_RE = re.compile(
    r"(?P<num>\d{1,3}(?:,\d{2,3})*(?:\.\d+)?|\d+(?:\.\d+)?)\s*(?P<mult>k|lac|lakh|lakhs|crore|m|mn|million)?",
    re.IGNORECASE,
)
_MULTIPLIERS = {"k": 1_000, "lac": 100_000, "lakh": 100_000, "lakhs": 100_000,
                "crore": 10_000_000, "m": 1_000_000, "mn": 1_000_000, "million": 1_000_000}


def normalize_salary(
    raw: str | None,
    *,
    min_value: float | str | None = None,
    max_value: float | str | None = None,
    currency: str | None = None,
    period: str | None = None,
) -> NormalizedSalary:
    """Parse structured and/or free-text salary information.

    '80,000 - 120,000 PKR per month', 'Rs. 1.2 lac', 'USD 60k/year' all resolve correctly.
    Returns all-None when nothing trustworthy is found (never guesses a number).
    """
    detected_currency = _detect_currency(currency) or _detect_currency(raw)
    detected_period = _detect_period(period) or _detect_period(raw)

    lo = _coerce_decimal(min_value)
    hi = _coerce_decimal(max_value)

    if lo is None and hi is None and raw:
        lo, hi = _parse_amount_range(raw)

    if lo is not None and hi is not None and lo > hi:
        lo, hi = hi, lo
    # Reject implausible values rather than polluting filters.
    for value in (lo, hi):
        if value is not None and (value <= 0 or value > Decimal("1e12")):
            return NormalizedSalary(None, None, detected_currency, detected_period)

    if lo is None and hi is None:
        return NormalizedSalary(None, None, None, None)

    if detected_currency is None:
        detected_currency = "PKR"
    if detected_period is None:
        reference = hi or lo or Decimal(0)
        if detected_currency == "PKR":
            detected_period = "month" if reference < Decimal("1500000") else "year"
        else:
            detected_period = "year" if reference > Decimal("10000") else "month"
    return NormalizedSalary(lo, hi, detected_currency, detected_period)


def _detect_currency(value: str | None) -> str | None:
    if not value:
        return None
    low = value.lower()
    for token, code in _CURRENCY_MAP.items():
        if token in low:
            return code
    return None


def _detect_period(value: str | None) -> str | None:
    if not value:
        return None
    for pattern, period in _PERIOD_MAP:
        if pattern.search(value):
            return period
    return None


def _coerce_decimal(value: float | str | None) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        dec = Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return None
    return dec if dec > 0 else None


def _parse_amount_range(raw: str) -> tuple[Decimal | None, Decimal | None]:
    text = raw.lower()
    # Ignore obvious non-salary numbers (years, dates, phone numbers).
    text = re.sub(r"\b(19|20)\d{2}\b", " ", text)
    amounts: list[Decimal] = []
    for match in _AMOUNT_RE.finditer(text):
        num = match.group("num").replace(",", "")
        try:
            value = Decimal(num)
        except InvalidOperation:
            continue
        mult = match.group("mult")
        if mult:
            value *= _MULTIPLIERS[mult.lower()]
        if value < 100:  # too small to be a salary without a multiplier
            continue
        amounts.append(value)
        if len(amounts) == 2:
            break
    if not amounts:
        return None, None
    if len(amounts) == 1:
        return amounts[0], None
    return amounts[0], amounts[1]


# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------

_DATE_FORMATS = (
    "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ",
    "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y",
    "%d %b %Y", "%d %B %Y", "%b %d, %Y", "%B %d, %Y", "%a, %d %b %Y %H:%M:%S %z",
)
_RELATIVE_RE = re.compile(r"(\d+)\s*(minute|hour|day|week|month)s?\s+ago", re.IGNORECASE)
_DEADLINE_RE = re.compile(
    r"(?:last date|closing date|apply before|deadline|applications? close[sd]?|valid till|last day)"
    # Allow short connective text ("... to apply:") but never skip over another number.
    r"[^0-9]{0,30}"
    r"([0-9]{1,2}[\s\-/][a-z0-9]{2,9}[\s\-/][0-9]{2,4}|[0-9]{4}-[0-9]{2}-[0-9]{2}|"
    r"[a-z]{3,9}\s+[0-9]{1,2},?\s+[0-9]{4})",
    re.IGNORECASE,
)


def parse_datetime(value: str | int | float | datetime | date | None) -> datetime | None:
    """Best-effort timezone-aware datetime parsing for anything a source may send."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        ts = float(value)
        if ts > 1e11:  # milliseconds
            ts /= 1000
        try:
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None

    text = str(value).strip()
    if not text:
        return None

    relative = _RELATIVE_RE.search(text)
    if relative:
        amount = int(relative.group(1))
        unit = relative.group(2).lower()
        delta = {
            "minute": timedelta(minutes=amount),
            "hour": timedelta(hours=amount),
            "day": timedelta(days=amount),
            "week": timedelta(weeks=amount),
            "month": timedelta(days=30 * amount),
        }[unit]
        return datetime.now(timezone.utc) - delta
    if re.fullmatch(r"(just now|today)", text, re.IGNORECASE):
        return datetime.now(timezone.utc)
    if re.fullmatch(r"yesterday", text, re.IGNORECASE):
        return datetime.now(timezone.utc) - timedelta(days=1)

    iso_candidate = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(iso_candidate)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        pass

    for fmt in _DATE_FORMATS:
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def extract_deadline(text: str | None) -> datetime | None:
    """Find an application deadline mentioned in free text (common on government ads)."""
    if not text:
        return None
    match = _DEADLINE_RE.search(text)
    if not match:
        return None
    parsed = parse_datetime(match.group(1))
    if parsed is None:
        return None
    now = datetime.now(timezone.utc)
    # Ignore nonsense: deadlines far in the past or more than 2 years out.
    if parsed < now - timedelta(days=365) or parsed > now + timedelta(days=730):
        return None
    return parsed


# ---------------------------------------------------------------------------
# Skills
# ---------------------------------------------------------------------------

SKILL_DICTIONARY: dict[str, tuple[str, ...]] = {
    "Python": ("python", "python3", "py"),
    "JavaScript": ("javascript", "js", "es6"),
    "TypeScript": ("typescript", "ts"),
    "React": ("react", "reactjs", "react.js"),
    "Next.js": ("next.js", "nextjs"),
    "Node.js": ("node.js", "nodejs", "node"),
    "Django": ("django",),
    "FastAPI": ("fastapi",),
    "Laravel": ("laravel",),
    "PHP": ("php",),
    "Java": ("java", "core java"),
    "Spring Boot": ("spring boot", "springboot"),
    "C#": ("c#", "csharp", ".net", "dotnet", "asp.net"),
    "C++": ("c++", "cpp"),
    "Go": ("golang",),
    "Rust": ("rust",),
    "Ruby on Rails": ("ruby on rails", "rails"),
    "Flutter": ("flutter", "dart"),
    "React Native": ("react native",),
    "Android": ("android", "kotlin"),
    "iOS": ("ios", "swift", "swiftui"),
    "SQL": ("sql", "t-sql", "pl/sql"),
    "PostgreSQL": ("postgresql", "postgres"),
    "MySQL": ("mysql", "mariadb"),
    "MongoDB": ("mongodb", "mongo"),
    "Redis": ("redis",),
    "Docker": ("docker", "containerization"),
    "Kubernetes": ("kubernetes", "k8s"),
    "AWS": ("aws", "amazon web services"),
    "Azure": ("azure", "microsoft azure"),
    "GCP": ("gcp", "google cloud"),
    "Terraform": ("terraform",),
    "CI/CD": ("ci/cd", "cicd", "continuous integration"),
    "Linux": ("linux", "ubuntu", "centos"),
    "Machine Learning": ("machine learning", "ml", "scikit-learn", "sklearn"),
    "Deep Learning": ("deep learning", "pytorch", "tensorflow", "keras"),
    "NLP": ("nlp", "natural language processing", "llm", "large language model"),
    "Computer Vision": ("computer vision", "opencv"),
    "Data Analysis": ("data analysis", "pandas", "numpy", "data analytics"),
    "Power BI": ("power bi", "powerbi"),
    "Tableau": ("tableau",),
    "Excel": ("excel", "ms excel", "advanced excel"),
    "ETL": ("etl", "data pipeline", "airflow"),
    "Cybersecurity": ("cybersecurity", "information security", "infosec", "soc analyst"),
    "Penetration Testing": ("penetration testing", "pentest", "ethical hacking"),
    "Networking": ("networking", "ccna", "ccnp", "routing and switching"),
    "Figma": ("figma",),
    "Adobe Photoshop": ("photoshop", "adobe photoshop"),
    "Adobe Illustrator": ("illustrator", "adobe illustrator"),
    "UI/UX Design": ("ui/ux", "ux design", "ui design", "user experience"),
    "Graphic Design": ("graphic design", "graphics designing"),
    "SEO": ("seo", "search engine optimization"),
    "Digital Marketing": ("digital marketing", "performance marketing"),
    "Social Media Marketing": ("social media marketing", "smm"),
    "Content Writing": ("content writing", "copywriting", "content creation"),
    "Sales": ("sales", "business development", "bd"),
    "Customer Support": ("customer support", "customer service", "call center", "csr"),
    "Accounting": ("accounting", "bookkeeping", "quickbooks"),
    "Financial Analysis": ("financial analysis", "financial modeling", "fp&a"),
    "Taxation": ("taxation", "tax filing", "income tax"),
    "ACCA": ("acca",),
    "CA": ("chartered accountant", "ca finalist"),
    "Recruitment": ("recruitment", "talent acquisition", "hiring"),
    "Project Management": ("project management", "pmp", "scrum master", "agile"),
    "Supply Chain": ("supply chain", "logistics", "procurement"),
    "Teaching": ("teaching", "lecturer", "lesson planning"),
    "Nursing": ("nursing", "patient care"),
    "AutoCAD": ("autocad", "auto cad"),
    "SolidWorks": ("solidworks",),
    "Civil Engineering": ("civil engineering", "site engineer"),
    "Electrical Engineering": ("electrical engineering", "electrical design"),
    "Mechanical Engineering": ("mechanical engineering",),
    "Communication Skills": ("communication skills", "verbal communication"),
    "English Proficiency": ("english proficiency", "fluent english", "spoken english"),
    "MS Office": ("ms office", "microsoft office"),
    "ERP": ("erp", "sap", "oracle erp", "odoo"),
    "Salesforce": ("salesforce", "crm"),
    "QA Testing": ("qa", "quality assurance", "manual testing", "test automation", "selenium"),
    "WordPress": ("wordpress", "woocommerce"),
    "Shopify": ("shopify",),
    "Video Editing": ("video editing", "premiere pro", "after effects"),
}

_SKILL_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        canonical,
        re.compile(r"(?<![a-z0-9])(?:%s)(?![a-z0-9])" % "|".join(re.escape(a) for a in aliases), re.IGNORECASE),
    )
    for canonical, aliases in SKILL_DICTIONARY.items()
]


def extract_skills(*texts: str | None, limit: int = 25) -> list[str]:
    """Dictionary-based skill extraction. Deterministic, fast and free.

    The AI layer can augment this later via `AISkillExtraction` without replacing it.
    """
    haystack = " ".join(t for t in texts if t)
    if not haystack.strip():
        return []
    found: list[str] = []
    for canonical, pattern in _SKILL_PATTERNS:
        if pattern.search(haystack):
            found.append(canonical)
            if len(found) >= limit:
                break
    return found


def normalize_skill_list(values: Iterable[str] | None, limit: int = 40) -> list[str]:
    """De-duplicate and canonicalise a user- or source-supplied skill list."""
    if not values:
        return []
    alias_to_canonical = {
        alias: canonical for canonical, aliases in SKILL_DICTIONARY.items() for alias in aliases
    }
    alias_to_canonical.update({c.lower(): c for c in SKILL_DICTIONARY})

    seen: dict[str, None] = {}
    for value in values:
        if not value:
            continue
        cleaned = collapse_whitespace(str(value))[:60]
        if not cleaned:
            continue
        canonical = alias_to_canonical.get(cleaned.lower(), cleaned)
        seen.setdefault(canonical, None)
        if len(seen) >= limit:
            break
    return list(seen)


def skill_slug(name: str) -> str:
    return slugify(name, max_length=110)
