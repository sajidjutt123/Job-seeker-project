"""Canonical domain vocabularies.

These are plain `str` enums stored as VARCHAR + CHECK-free columns on purpose: adding a new
category or employment type must not require a database migration or a table lock. Validation
happens in the application layer where it can evolve cheaply.
"""

from __future__ import annotations

from enum import StrEnum


class UserRole(StrEnum):
    USER = "user"
    ADMIN = "admin"
    EMPLOYER = "employer"  # reserved for the future employer platform


class UserStatus(StrEnum):
    ACTIVE = "active"
    PENDING_VERIFICATION = "pending_verification"
    SUSPENDED = "suspended"
    DELETED = "deleted"


class JobStatus(StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    CLOSED = "closed"
    REMOVED = "removed"
    PENDING_REVIEW = "pending_review"
    UNKNOWN = "unknown"


class JobOrigin(StrEnum):
    """Distinguishes aggregated listings from directly posted employer listings."""

    AGGREGATED = "aggregated"
    DIRECT = "direct"


class EmploymentType(StrEnum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    TEMPORARY = "temporary"
    INTERNSHIP = "internship"
    FREELANCE = "freelance"
    VOLUNTEER = "volunteer"
    UNKNOWN = "unknown"


class ExperienceLevel(StrEnum):
    INTERN = "intern"
    FRESH_GRADUATE = "fresh_graduate"
    ENTRY = "entry"
    MID = "mid"
    SENIOR = "senior"
    LEAD = "lead"
    EXECUTIVE = "executive"
    UNKNOWN = "unknown"


class WorkMode(StrEnum):
    ONSITE = "onsite"
    HYBRID = "hybrid"
    REMOTE = "remote"
    UNKNOWN = "unknown"


class SourceType(StrEnum):
    API = "api"
    RSS = "rss"
    PARTNER_FEED = "partner_feed"
    CAREER_PAGE = "career_page"
    GOVERNMENT_PORTAL = "government_portal"
    EMPLOYER_DIRECT = "employer_direct"
    SEED = "seed"


class SourceStatus(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILING = "failing"
    DISABLED = "disabled"
    NEEDS_CREDENTIALS = "needs_credentials"
    UNKNOWN = "unknown"


class SourceRunStatus(StrEnum):
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"


class JobEventType(StrEnum):
    CREATED = "created"
    UPDATED = "updated"
    REACTIVATED = "reactivated"
    EXPIRED = "expired"
    CLOSED = "closed"
    REMOVED = "removed"
    HIDDEN = "hidden"
    RESTORED = "restored"
    DUPLICATE_LINKED = "duplicate_linked"
    QUALITY_RESCORED = "quality_rescored"
    APPLY_URL_CHECKED = "apply_url_checked"


class NotificationChannel(StrEnum):
    EMAIL = "email"
    IN_APP = "in_app"
    PUSH = "push"        # architected, not yet delivered
    WHATSAPP = "whatsapp"
    TELEGRAM = "telegram"


class NotificationStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    READ = "read"


class AlertFrequency(StrEnum):
    INSTANT = "instant"
    DAILY = "daily"
    WEEKLY = "weekly"


class ReportReason(StrEnum):
    EXPIRED = "expired"
    SPAM = "spam"
    SCAM = "scam"
    DUPLICATE = "duplicate"
    WRONG_INFORMATION = "wrong_information"
    BROKEN_LINK = "broken_link"
    OFFENSIVE = "offensive"
    OTHER = "other"


class ReportStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"
    REJECTED = "rejected"


class AnalyticsEventType(StrEnum):
    SEARCH = "search"
    JOB_VIEW = "job_view"
    APPLY_CLICK = "apply_click"
    JOB_SAVE = "job_save"
    JOB_UNSAVE = "job_unsave"
    ALERT_CREATED = "alert_created"
    ALERT_OPENED = "alert_opened"
    SIGNUP = "signup"
    LOGIN = "login"


# --- Job categories --------------------------------------------------------
class JobCategorySlug(StrEnum):
    SOFTWARE_ENGINEERING = "software-engineering"
    DATA_SCIENCE = "data-science"
    AI_ML = "ai-ml"
    CYBERSECURITY = "cybersecurity"
    NETWORKING = "networking"
    DEVOPS = "devops"
    FINANCE = "finance"
    ACCOUNTING = "accounting"
    HR = "human-resources"
    MARKETING = "marketing"
    SALES = "sales"
    EDUCATION = "education"
    MEDICAL = "medical"
    ENGINEERING = "engineering"
    CONSTRUCTION = "construction"
    LEGAL = "legal"
    ADMINISTRATION = "administration"
    CUSTOMER_SUPPORT = "customer-support"
    DESIGN = "design"
    OPERATIONS = "operations"
    GOVERNMENT = "government"
    INTERNSHIPS = "internships"
    OTHER = "other"


CATEGORY_LABELS: dict[str, str] = {
    JobCategorySlug.SOFTWARE_ENGINEERING: "Software Engineering",
    JobCategorySlug.DATA_SCIENCE: "Data Science",
    JobCategorySlug.AI_ML: "AI / ML",
    JobCategorySlug.CYBERSECURITY: "Cybersecurity",
    JobCategorySlug.NETWORKING: "Networking",
    JobCategorySlug.DEVOPS: "DevOps",
    JobCategorySlug.FINANCE: "Finance",
    JobCategorySlug.ACCOUNTING: "Accounting",
    JobCategorySlug.HR: "HR",
    JobCategorySlug.MARKETING: "Marketing",
    JobCategorySlug.SALES: "Sales",
    JobCategorySlug.EDUCATION: "Education",
    JobCategorySlug.MEDICAL: "Medical",
    JobCategorySlug.ENGINEERING: "Engineering",
    JobCategorySlug.CONSTRUCTION: "Construction",
    JobCategorySlug.LEGAL: "Legal",
    JobCategorySlug.ADMINISTRATION: "Administration",
    JobCategorySlug.CUSTOMER_SUPPORT: "Customer Support",
    JobCategorySlug.DESIGN: "Design",
    JobCategorySlug.OPERATIONS: "Operations",
    JobCategorySlug.GOVERNMENT: "Government",
    JobCategorySlug.INTERNSHIPS: "Internships",
    JobCategorySlug.OTHER: "Other",
}
