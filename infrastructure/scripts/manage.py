#!/usr/bin/env python
"""RozgarPK management CLI.

    python infrastructure/scripts/manage.py sync-sources
    python infrastructure/scripts/manage.py create-admin --email you@example.com
    python infrastructure/scripts/manage.py seed --enable
    python infrastructure/scripts/manage.py seed --clear
    python infrastructure/scripts/manage.py ingest --source <slug>
    python infrastructure/scripts/manage.py expire
    python infrastructure/scripts/manage.py alerts --frequency daily
    python infrastructure/scripts/manage.py stats
"""

from __future__ import annotations

import argparse
import getpass
import sys
from datetime import datetime, timezone

from sqlalchemy import delete, func, select

from pakjobs_core.config import settings
from pakjobs_core.db.session import session_scope
from pakjobs_core.domain.enums import UserRole, UserStatus
from pakjobs_core.logging import configure_logging, get_logger
from pakjobs_core.models import Job, JobSource, Profile, SourceRun, User
from pakjobs_core.services.expiration import ExpirationService
from pakjobs_core.services.ingestion import IngestionService
from pakjobs_core.services.security import hash_password
from pakjobs_core.services.source_registry import sync_default_sources

logger = get_logger("manage")


def cmd_sync_sources(_: argparse.Namespace) -> int:
    with session_scope() as session:
        result = sync_default_sources(session)
    print(f"Sources synced: {result['created']} created, {result['updated']} refreshed.")
    return 0


def cmd_create_admin(args: argparse.Namespace) -> int:
    email = (args.email or settings.bootstrap_admin_email or "").strip().lower()
    if not email:
        print("Provide --email or set BOOTSTRAP_ADMIN_EMAIL.", file=sys.stderr)
        return 1

    password = args.password or settings.bootstrap_admin_password
    if not password:
        password = getpass.getpass("Password: ")
        if password != getpass.getpass("Confirm password: "):
            print("Passwords do not match.", file=sys.stderr)
            return 1

    with session_scope() as session:
        user = session.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if user:
            user.role = UserRole.ADMIN
            user.status = UserStatus.ACTIVE
            user.password_hash = hash_password(password)
            user.email_verified_at = user.email_verified_at or datetime.now(timezone.utc)
            user.token_version += 1  # invalidate old sessions after a privilege change
            print(f"Promoted existing user {email} to admin and reset their password.")
        else:
            user = User(
                email=email,
                password_hash=hash_password(password),
                role=UserRole.ADMIN,
                status=UserStatus.ACTIVE,
                email_verified_at=datetime.now(timezone.utc),
            )
            session.add(user)
            session.flush()
            session.add(Profile(user_id=user.id, full_name="Administrator"))
            print(f"Created admin user {email}.")
    return 0


def cmd_seed(args: argparse.Namespace) -> int:
    if settings.is_production:
        print("Refusing to run seed operations in production.", file=sys.stderr)
        return 1

    with session_scope() as session:
        source = session.execute(
            select(JobSource).where(JobSource.slug == "dev-sample-data")
        ).scalar_one_or_none()
        if source is None:
            sync_default_sources(session, enable_seed=True)
            source = session.execute(
                select(JobSource).where(JobSource.slug == "dev-sample-data")
            ).scalar_one()

        if args.clear:
            removed = session.execute(delete(Job).where(Job.source_id == source.id)).rowcount
            session.execute(delete(SourceRun).where(SourceRun.source_id == source.id))
            source.enabled = False
            source.total_jobs_collected = 0
            print(f"Removed {removed} development sample jobs.")
            return 0

        if not settings.enable_seed_sources:
            print("Set ENABLE_SEED_SOURCES=true to load sample data.", file=sys.stderr)
            return 1

        source.enabled = True
        run = IngestionService(session).run_source(source, trigger="cli")
        print(
            f"Seed run {run.status}: {run.created_count} created, {run.updated_count} updated, "
            f"{run.rejected_count} rejected."
        )
    return 0


def cmd_ingest(args: argparse.Namespace) -> int:
    with session_scope() as session:
        query = select(JobSource).where(JobSource.enabled.is_(True))
        if args.source:
            query = select(JobSource).where(JobSource.slug == args.source)
        sources = list(session.execute(query).scalars().all())

        if not sources:
            print("No matching enabled sources.", file=sys.stderr)
            return 1

        service = IngestionService(session)
        for source in sources:
            run = service.run_source(source, trigger="cli", limit=args.limit)
            status = "OK " if run.status != "failed" else "FAIL"
            print(
                f"[{status}] {source.slug:32} created={run.created_count:<4} "
                f"updated={run.updated_count:<4} dupes={run.duplicate_count:<3} "
                f"rejected={run.rejected_count:<3} {run.error_message or ''}"
            )
    return 0


def cmd_expire(args: argparse.Namespace) -> int:
    with session_scope() as session:
        report = ExpirationService(session).run_all(
            unseen_days=args.unseen_days, check_urls=args.check_urls
        )
    for key, value in report.as_dict().items():
        print(f"  {key}: {value}")
    return 0


def cmd_alerts(args: argparse.Namespace) -> int:
    sys.path.insert(0, "apps/worker")
    from worker.tasks import dispatch_alerts

    result = dispatch_alerts(frequency=args.frequency)
    for key, value in result.items():
        print(f"  {key}: {value}")
    return 0


def cmd_stats(_: argparse.Namespace) -> int:
    with session_scope() as session:
        total = session.execute(select(func.count(Job.id))).scalar_one()
        by_status = session.execute(
            select(Job.status, func.count(Job.id)).group_by(Job.status)
        ).all()
        users = session.execute(select(func.count(User.id))).scalar_one()
        sources = session.execute(
            select(JobSource.slug, JobSource.enabled, JobSource.status, JobSource.total_jobs_collected)
            .order_by(JobSource.priority)
        ).all()

        print(f"Jobs: {total}")
        for status, count in by_status:
            print(f"  {status:16} {count}")
        print(f"Users: {users}")
        print("Sources:")
        for slug, enabled, status, collected in sources:
            flag = "on " if enabled else "off"
            print(f"  [{flag}] {slug:32} {status:18} collected={collected}")
    return 0


def main() -> int:
    configure_logging(settings.log_level, settings.log_json)

    parser = argparse.ArgumentParser(description="RozgarPK management CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("sync-sources", help="Create/refresh the default source registry")

    admin = sub.add_parser("create-admin", help="Create or promote an admin user")
    admin.add_argument("--email")
    admin.add_argument("--password", help="Omit to be prompted securely")

    seed = sub.add_parser("seed", help="Load or clear development sample jobs")
    seed.add_argument("--enable", action="store_true", help="Load sample data (default)")
    seed.add_argument("--clear", action="store_true", help="Remove all sample data")

    ingest = sub.add_parser("ingest", help="Run ingestion synchronously")
    ingest.add_argument("--source", help="Source slug (default: all enabled)")
    ingest.add_argument("--limit", type=int, help="Max jobs to fetch per source")

    expire = sub.add_parser("expire", help="Run the expiration engine")
    expire.add_argument("--unseen-days", type=int, default=21)
    expire.add_argument("--check-urls", action="store_true", help="Also verify apply URLs (slow)")

    alerts = sub.add_parser("alerts", help="Dispatch job alert digests")
    alerts.add_argument("--frequency", default="daily", choices=["instant", "daily", "weekly"])

    sub.add_parser("stats", help="Print a database summary")

    args = parser.parse_args()
    handlers = {
        "sync-sources": cmd_sync_sources,
        "create-admin": cmd_create_admin,
        "seed": cmd_seed,
        "ingest": cmd_ingest,
        "expire": cmd_expire,
        "alerts": cmd_alerts,
        "stats": cmd_stats,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
