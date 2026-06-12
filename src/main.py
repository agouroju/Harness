"""Entry point: --check env, --once single run, --loop autonomous schedule."""

import argparse
import sys
import time
import traceback


def check() -> bool:
    from . import config

    missing = config.missing_required()
    if missing:
        print(f"✗ Missing required env vars: {', '.join(missing)} (see .env.example)")
        return False
    print("✓ Required env vars present")

    from . import db
    try:
        ch = db.client()
        db.init(ch)
        print(f"✓ ClickHouse reachable, schema ready ({config.CLICKHOUSE_HOST})")
    except Exception as err:
        print(f"✗ ClickHouse: {err}")
        return False

    from . import senso
    try:
        me = senso.whoami()
        print(f"✓ Senso authenticated: {str(me)[:120]}")
        dests = senso.destinations()
        print(f"✓ Senso destinations: {str(dests)[:200]}")
    except Exception as err:
        print(f"✗ Senso: {err}")
        return False

    if config.LANGFUSE_PUBLIC_KEY:
        print("✓ Langfuse tracing enabled")
    else:
        print("- Langfuse keys not set (tracing disabled)")
    return True


def main():
    parser = argparse.ArgumentParser(description="AI DevTool Radar")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="validate env + connectivity")
    group.add_argument("--once", action="store_true", help="one full autonomous run")
    group.add_argument("--loop", action="store_true", help="run forever on RADAR_INTERVAL_MIN")
    group.add_argument("--list-repos", action="store_true", help="print the repository watchlist")
    group.add_argument("--add-repo", metavar="OWNER/REPO", help="add a GitHub repo to the watchlist")
    group.add_argument("--remove-repo", metavar="OWNER/REPO", help="remove a GitHub repo from the watchlist")
    group.add_argument("--list-feeds", action="store_true", help="print the feed watchlist")
    group.add_argument("--add-feed", metavar="URL", help="add an RSS/Atom feed to the watchlist")
    group.add_argument("--remove-feed", metavar="URL", help="remove an RSS/Atom feed from the watchlist")
    group.add_argument("--sync-sources", action="store_true",
                       help="reconcile Airbyte pipelines with the watchlist files")
    parser.add_argument(
        "--direct-ingest",
        action="store_true",
        help="legacy mode: pull HN/GitHub directly from Python before analysis",
    )
    args = parser.parse_args()

    if args.check:
        sys.exit(0 if check() else 1)

    if args.list_repos:
        from . import config

        print(f"Repository watchlist ({len(config.TRACKED_REPOS)} repos):")
        for repo in config.TRACKED_REPOS:
            print(f"- {repo}")
        print(f"\nEdit file: {config.tracked_repos_path()}")
        return

    if args.add_repo:
        from . import config, watchlist

        try:
            repo, changed = watchlist.add_repo(args.add_repo)
        except ValueError as err:
            print(f"✗ {err}")
            sys.exit(2)
        action = "Added" if changed else "Already tracked"
        print(f"{action}: {repo}")
        print(f"Watchlist file: {config.tracked_repos_path()}")
        print("Note: update the Airbyte GitHub source separately if you want Airbyte to sync this repo too.")
        return

    if args.remove_repo:
        from . import config, watchlist

        try:
            repo, changed = watchlist.remove_repo(args.remove_repo)
        except ValueError as err:
            print(f"✗ {err}")
            sys.exit(2)
        action = "Removed" if changed else "Not tracked"
        print(f"{action}: {repo}")
        print(f"Watchlist file: {config.tracked_repos_path()}")
        print("Note: update the Airbyte GitHub source separately if you want Airbyte to stop syncing this repo too.")
        return

    if args.list_feeds:
        from . import config

        print(f"Feed watchlist ({len(config.TRACKED_FEEDS)} feeds):")
        for feed in config.TRACKED_FEEDS:
            print(f"- {feed}")
        print(f"\nEdit file: {config.tracked_feeds_path()}")
        return

    if args.add_feed or args.remove_feed:
        from . import config, watchlist

        try:
            if args.add_feed:
                feed, changed = watchlist.add_feed(args.add_feed)
                action = "Added" if changed else "Already tracked"
            else:
                feed, changed = watchlist.remove_feed(args.remove_feed)
                action = "Removed" if changed else "Not tracked"
        except ValueError as err:
            print(f"✗ {err}")
            sys.exit(2)
        print(f"{action}: {feed}")
        print(f"Watchlist file: {config.tracked_feeds_path()}")
        if changed:
            print("Run `python -m src.main --sync-sources` to apply this to Airbyte.")
        return

    if args.sync_sources:
        import importlib

        from . import airbyte, config

        importlib.reload(config)  # pick up watchlist edits made this process
        if not airbyte.configured():
            print("✗ Airbyte API is not configured (set AIRBYTE_CLIENT_ID/SECRET in .env)")
            sys.exit(2)
        from . import pipelines

        report = pipelines.reconcile()
        print(f"Created pipelines: {report['created'] or 'none'}")
        print(f"Deleted pipelines: {report['deleted'] or 'none'}")
        print(f"Initial syncs triggered: {report['synced'] or 'none'}")
        print(f"GitHub source repositories set: {report['github_repos']}")
        return

    from . import agent, config

    if args.once:
        agent.run_once(ingest_first=args.direct_ingest)
        return

    while True:
        try:
            agent.run_once(ingest_first=args.direct_ingest)
        except Exception:
            traceback.print_exc()
        print(f"Sleeping {config.RADAR_INTERVAL_MIN} min...")
        time.sleep(config.RADAR_INTERVAL_MIN * 60)


if __name__ == "__main__":
    main()
