"""Settings, read once from the environment."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

REQUIRED = (
    "SWITCH_API_ENDPOINT",
    "SWITCH_AGENT_ID",
    "SWITCH_API_TOKEN",
    "ANTHROPIC_API_KEY",
    "TRIAGER_INTAKE_ROOM_ID",
)


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Config:
    switch_endpoint: str
    agent_id: str
    switch_token: str = field(repr=False)
    anthropic_api_key: str = field(repr=False)
    intake_room_id: str
    team: str
    model: str
    effort: str
    demo_app_main: Path
    db_path: Path

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Config":
        env = os.environ if env is None else env
        missing = [name for name in REQUIRED if not env.get(name)]
        if missing:
            raise ConfigError("missing environment variables: " + ", ".join(missing))
        return cls(
            switch_endpoint=env["SWITCH_API_ENDPOINT"].rstrip("/"),
            agent_id=env["SWITCH_AGENT_ID"],
            switch_token=env["SWITCH_API_TOKEN"],
            anthropic_api_key=env["ANTHROPIC_API_KEY"],
            intake_room_id=env["TRIAGER_INTAKE_ROOM_ID"],
            team=env.get("TRIAGER_TEAM", "shop"),
            model=env.get("TRIAGER_MODEL", "claude-opus-5-5"),
            effort=env.get("TRIAGER_EFFORT", "low"),
            demo_app_main=Path(env.get("DEMO_APP_MAIN", "../demo-app/app/main.py")),
            db_path=Path(env.get("TRIAGER_DB", "triager.db")),
        )
