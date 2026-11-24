"""Run the Triager: `triager` to connect and work, `triager --check` to validate setup."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from .agent import TeamConfig, Triager
from .config import Config, ConfigError
from .decision import ClaudeDecider
from .rules import load_rules
from .state import Store
from .switch_client import SwitchClient


async def run(config: Config, rules: list[str]) -> None:
    import anthropic

    switch = SwitchClient(config.switch_endpoint, config.agent_id, config.switch_token)
    triager = Triager(
        switch=switch,
        decider=ClaudeDecider(
            anthropic.AsyncAnthropic(api_key=config.anthropic_api_key),
            model=config.model,
            effort=config.effort,
        ),
        store=Store(config.db_path),
        team=TeamConfig(team=config.team, intake_room_id=config.intake_room_id),
        rules=rules,
    )
    try:
        async for event in switch.events():
            try:
                await triager.handle(event)
            except Exception:
                logging.exception("handling %s event failed", event.type)
    finally:
        await switch.aclose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="triager")
    parser.add_argument("--check", action="store_true", help="validate settings and exit")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    try:
        config = Config.from_env()
    except ConfigError as exc:
        print(f"config: {exc}", file=sys.stderr)
        return 2

    rules = load_rules(config.demo_app_main)
    print(f"switch: {config.switch_endpoint} as {config.agent_id}")
    print(f"team: {config.team}, intake room: {config.intake_room_id}")
    print(f"model: {config.model} (effort {config.effort})")
    print(f"business rules: {len(rules)}")
    if args.check:
        return 0

    try:
        asyncio.run(run(config, rules))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
