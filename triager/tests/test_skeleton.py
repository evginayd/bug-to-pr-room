from pathlib import Path

import pytest

from triager.config import Config, ConfigError
from triager.rules import load_rules
from triager.state import MAX_QUESTIONS, Stage, can_move

DEMO_MAIN = Path(__file__).resolve().parents[2] / "demo-app" / "app" / "main.py"

ENV = {
    "SWITCH_API_ENDPOINT": "http://localhost:8000/",
    "SWITCH_AGENT_ID": "agent-1",
    "SWITCH_API_TOKEN": "test-token",
    "ANTHROPIC_API_KEY": "test-key",
    "TRIAGER_INTAKE_ROOM_ID": "intake",
}


def test_rules_are_read_from_the_demo_app():
    rules = load_rules(DEMO_MAIN)
    assert len(rules) == 4
    assert "SAVE10 takes 10 percent off the cart subtotal." in rules[1]
    assert rules[3].startswith("Removing a product that is not in the cart")


def test_config_reads_env_and_hides_secrets():
    config = Config.from_env(ENV)
    assert config.switch_endpoint == "http://localhost:8000"
    assert config.model == "claude-opus-5-5"
    assert "test-token" not in repr(config)
    assert "test-key" not in repr(config)


def test_config_names_what_is_missing():
    with pytest.raises(ConfigError, match="SWITCH_API_TOKEN"):
        Config.from_env({k: v for k, v in ENV.items() if k != "SWITCH_API_TOKEN"})


def test_a_report_cannot_ask_twice_or_reopen():
    assert can_move(Stage.NEW, Stage.AWAITING_ANSWERS)
    assert not can_move(Stage.AWAITING_ANSWERS, Stage.AWAITING_ANSWERS)
    assert not can_move(Stage.FIXED, Stage.ROOM_OPEN)
    assert MAX_QUESTIONS == 2
