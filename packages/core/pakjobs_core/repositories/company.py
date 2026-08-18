from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from pakjobs_core.models import Company
from pakjobs_core.pipeline.text import slugify


class CompanyRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_or_create(
        self,
        *,
        name: str,
        matching_key: str,
        website: str | None = None,
        logo_url: str | None = None,
        industry: str | None = None,
    ) -> Company:
        """Merge employers across sources on the normalized matching key."""
        key = (matching_key or name).strip().lower()[:240]
        existing = self.session.execute(
            select(Company).where(Company.normalized_name == key)
        ).scalar_one_or_none()
        if existing:
            # Enrich progressively — never overwrite good data with nulls.
            if website and not existing.website:
                existing.website = website[:500]
            if logo_url and not existing.logo_url:
                existing.logo_url = logo_url[:1000]
            if industry and not existing.industry:
                existing.industry = industry[:160]
            return existing

        company = Company(
            name=name[:240],
            normalized_name=key,
            slug=self._unique_slug(name),
            website=website[:500] if website else None,
            logo_url=logo_url[:1000] if logo_url else None,
            industry=industry[:160] if industry else None,
        )
        self.session.add(company)
        self.session.flush()
        return company

    def _unique_slug(self, name: str) -> str:
        base = slugify(name, max_length=120) or "company"
        candidate = base
        n = 1
        while self.session.execute(select(Company.id).where(Company.slug == candidate)).first() is not None:
            n += 1
            candidate = f"{base}-{n}"
            if n > 50:
                candidate = f"{base}-{uuid.uuid4().hex[:6]}"
                break
        return candidate[:260]
