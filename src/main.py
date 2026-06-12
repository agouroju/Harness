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
    args = parser.parse_args()

    if args.check:
        sys.exit(0 if check() else 1)

    from . import agent, config

    if args.once:
        agent.run_once()
        return

    while True:
        try:
            agent.run_once()
        except Exception:
            traceback.print_exc()
        print(f"Sleeping {config.RADAR_INTERVAL_MIN} min...")
        time.sleep(config.RADAR_INTERVAL_MIN * 60)


if __name__ == "__main__":
    main()
