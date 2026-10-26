"""Command line: ``garmates serve|sync|reparse|demo|reset-password``."""

from __future__ import annotations

import argparse
import getpass
import logging
import os
import sys

from sqlalchemy import select

from .config import get_settings
from .db import init_engine, session_scope


def _init() -> None:
    settings = get_settings()
    settings.ensure_dirs()
    init_engine(settings.database_url)


def cmd_serve(args: argparse.Namespace) -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "garmates.app:create_app",
        factory=True,
        host=args.host or settings.host,
        port=args.port or settings.port,
        reload=args.reload,
        log_level="info",
        proxy_headers=settings.trust_proxy,
        forwarded_allow_ips="*" if settings.trust_proxy else None,
    )


def cmd_sync(args: argparse.Namespace) -> None:
    from .garmin.sync import sync_person
    from .models import GarminCredential

    _init()
    with session_scope() as db:
        ids = [args.person] if args.person else list(db.scalars(select(GarminCredential.person_id)))
    if not ids:
        print("No Garmin keys stored yet - add one in the dashboard's People page.")
        return
    for person_id in ids:
        print(f"Syncing person {person_id}…", flush=True)
        print(f"  -> {sync_person(person_id)}")


def cmd_reparse(args: argparse.Namespace) -> None:
    from .garmin.sync import reparse_all

    _init()
    print(f"Re-parsed {reparse_all(args.person)} rows from stored payloads.")


def cmd_verify(args: argparse.Namespace) -> None:
    import json

    from .models import Person
    from .verify import people_with_data, report

    _init()
    with session_scope() as db:
        demo_ids = set(db.scalars(select(Person.id).where(Person.is_demo.is_(True))))
        ids = [args.person] if args.person else [
            pid for pid in people_with_data(db) if pid not in demo_ids
        ]
        if not ids:
            print("No synced Garmin data yet - add a key on the People & keys page first.")
            return
        for person_id in ids:
            print(json.dumps(report(db, person_id), indent=2, default=str))


def cmd_demo(args: argparse.Namespace) -> None:
    from .demo import remove_demo, seed_demo

    _init()
    if args.remove:
        print(f"Removed {remove_demo()} demo profile(s).")
    else:
        print(f"Created demo profiles with ids {seed_demo()}.")


def cmd_reset_password(args: argparse.Namespace) -> None:
    from .models import Person
    from .security import MIN_PASSWORD_LENGTH, hash_password

    _init()
    password = getpass.getpass("New password: ")
    if len(password) < MIN_PASSWORD_LENGTH:
        sys.exit(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    with session_scope() as db:
        person = db.scalar(select(Person).where(Person.username == args.username.lower()))
        if person is None:
            sys.exit(f"No user called {args.username!r}.")
        person.password_hash = hash_password(password)
    print("Password updated.")


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    parser = argparse.ArgumentParser(prog="garmates")
    parser.add_argument("--data-dir", help="Use this data directory instead of ./data")
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="Run the web dashboard")
    serve.add_argument("--host")
    serve.add_argument("--port", type=int)
    serve.add_argument("--reload", action="store_true", help="Auto-reload on code changes")
    serve.set_defaults(func=cmd_serve)

    sync = sub.add_parser("sync", help="Sync Garmin data now (foreground)")
    sync.add_argument("--person", type=int, help="Only this person id")
    sync.set_defaults(func=cmd_sync)

    reparse = sub.add_parser("reparse", help="Rebuild tables from stored Garmin responses")
    reparse.add_argument("--person", type=int)
    reparse.set_defaults(func=cmd_reparse)

    verify = sub.add_parser("verify", help="Data-quality report on synced Garmin data")
    verify.add_argument("--person", type=int)
    verify.set_defaults(func=cmd_verify)

    demo = sub.add_parser("demo", help="Create (or --remove) two synthetic demo profiles")
    demo.add_argument("--remove", action="store_true")
    demo.set_defaults(func=cmd_demo)

    reset = sub.add_parser("reset-password", help="Set a new password for a user")
    reset.add_argument("username")
    reset.set_defaults(func=cmd_reset_password)

    args = parser.parse_args(argv)
    if args.data_dir:
        os.environ["GARMATES_DATA_DIR"] = args.data_dir
        get_settings.cache_clear()
    args.func(args)


if __name__ == "__main__":
    main()
