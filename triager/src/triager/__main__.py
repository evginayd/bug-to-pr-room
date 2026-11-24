"""Entry point. For now only `--check`, which validates settings and rules."""

from __future__ import annotations

import argparse
import sys

from .config import Config, ConfigError
from .rules import load_rules


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="triager")
    parser.add_argument("--check", action="store_true", help="validate settings and exit")
    args = parser.parse_args(argv)

    try:
        config = Config.from_env()
    except ConfigError as exc:
        print(f"config: {exc}", file=sys.stderr)
        return 2

    rules = load_rules(config.demo_app_main)
    print(f"switch: {config.switch_endpoint} as {config.agent_id}")
    print(f"model: {config.model}")
    print(f"business rules: {len(rules)}")

    if args.check:
        return 0
    print("the agent loop arrives in milestone 3", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
