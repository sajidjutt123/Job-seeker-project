"""All ORM models. Importing this package registers every table on `Base.metadata`."""

from pakjobs_core.db.base import Base
from pakjobs_core.models.alert import AlertMatch, JobAlert, Notification
from pakjobs_core.models.analytics import AnalyticsEvent, SearchLog
from pakjobs_core.models.company import Company
from pakjobs_core.models.education import (
    AdmissionCycle,
    Campus,
    Course,
    Institution,
    Program,
    Scholarship,
)
from pakjobs_core.models.job import (
    Job,
    JobCategory,
    JobDuplicate,
    JobEvent,
    JobLocation,
    JobReport,
    JobSkill,
    JobViewDaily,
    SavedJob,
    Skill,
)
from pakjobs_core.models.source import JobSource, SourceRun
from pakjobs_core.models.user import AdminAuditLog, Profile, RefreshToken, User, VerificationToken

__all__ = [
    "Base",
    "AdminAuditLog",
    "AdmissionCycle",
    "AlertMatch",
    "AnalyticsEvent",
    "Campus",
    "Company",
    "Course",
    "Institution",
    "Job",
    "JobAlert",
    "JobCategory",
    "JobDuplicate",
    "JobEvent",
    "JobLocation",
    "JobReport",
    "JobSkill",
    "JobSource",
    "JobViewDaily",
    "Notification",
    "Profile",
    "Program",
    "RefreshToken",
    "SavedJob",
    "Scholarship",
    "SearchLog",
    "Skill",
    "SourceRun",
    "User",
    "VerificationToken",
]
