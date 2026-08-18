"""Skill taxonomy maintenance shared by ingestion and profile services."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from pakjobs_core.models import Job, JobSkill, Skill
from pakjobs_core.pipeline.normalizer import SKILL_DICTIONARY, skill_slug


def get_or_create_skill(session: Session, name: str) -> Skill:
    slug = skill_slug(name)
    existing = session.execute(select(Skill).where(Skill.slug == slug)).scalar_one_or_none()
    if existing:
        return existing
    skill = Skill(
        slug=slug,
        name=name[:140],
        aliases=list(SKILL_DICTIONARY.get(name, ())),
    )
    session.add(skill)
    session.flush()
    return skill


def sync_job_skills(session: Session, job: Job, skill_names: list[str]) -> None:
    """Replace a job's skill links with the supplied canonical list (idempotent)."""
    if not skill_names:
        return
    desired = {skill_slug(n): n for n in skill_names if n}
    existing_links = session.execute(
        select(JobSkill, Skill).join(Skill, JobSkill.skill_id == Skill.id).where(JobSkill.job_id == job.id)
    ).all()
    existing_slugs = {skill.slug for _, skill in existing_links}

    for link, skill in existing_links:
        if skill.slug not in desired:
            session.delete(link)
            skill.usage_count = max(0, skill.usage_count - 1)

    for slug, name in desired.items():
        if slug in existing_slugs:
            continue
        skill = get_or_create_skill(session, name)
        session.add(JobSkill(job_id=job.id, skill_id=skill.id))
        skill.usage_count += 1
