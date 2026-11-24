import json
from types import SimpleNamespace

import pytest

from triager.decision import (
    DECISION_SCHEMA,
    ClaudeDecider,
    InvalidDecision,
    ReportContext,
    TriageUnavailable,
    build_prompt,
    parse_decision,
)

BUG = {
    "kind": "bug",
    "severity": "high",
    "slug": "save10-negative-total",
    "summary": "POST /carts/1/discount SAVE10 on 4.00 gives -6.00, expected 3.60",
    "duplicate_of": None,
    "questions": [],
    "reply": "Thanks! A developer and two agents are on it.",
}

CONTEXT = ReportContext(
    messages=["SAVE10 made my total -6.00"],
    rules=["Discount code SAVE10 takes 10 percent off the cart subtotal."],
    known_issues="- 2026-11-05 | negative quantity | https://github.com/o/r/pull/1",
    questions_allowed=True,
)


def test_a_bug_decision_parses():
    d = parse_decision(BUG, questions_allowed=True)
    assert (d.kind, d.severity, d.slug) == ("bug", "high", "save10-negative-total")


@pytest.mark.parametrize(
    "change, message",
    [
        ({"severity": None}, "severity"),
        ({"slug": "Bad Slug!"}, "slug"),
        ({"summary": " "}, "summary"),
        ({"kind": "rant"}, "kind"),
        ({"questions": ["why?"]}, "only for an unclear"),
    ],
)
def test_bad_bug_decisions_are_refused(change, message):
    with pytest.raises(InvalidDecision, match=message):
        parse_decision({**BUG, **change}, questions_allowed=True)


def test_a_duplicate_needs_no_slug():
    d = parse_decision(
        {**BUG, "severity": None, "slug": None, "summary": None,
         "duplicate_of": "https://github.com/o/r/pull/6"},
        questions_allowed=True,
    )
    assert d.duplicate_of.endswith("/pull/6")


def test_unclear_asks_one_or_two_questions_and_only_once():
    unclear = {**BUG, "kind": "unclear", "questions": ["Which code?", "What was in the cart?"]}
    assert len(parse_decision(unclear, questions_allowed=True).questions) == 2

    with pytest.raises(InvalidDecision, match="1 to 2"):
        parse_decision({**unclear, "questions": ["a", "b", "c"]}, questions_allowed=True)
    with pytest.raises(InvalidDecision, match="no questions left"):
        parse_decision(unclear, questions_allowed=False)


def test_the_prompt_carries_rules_known_issues_and_the_report():
    prompt = build_prompt(CONTEXT)
    assert "<business_rules>\n- Discount code SAVE10" in prompt
    assert "pull/1" in prompt
    assert "<report>\nSAVE10 made my total -6.00\n</report>" in prompt
    assert prompt.endswith("Questions allowed: yes")


def test_schema_is_strict():
    assert DECISION_SCHEMA["additionalProperties"] is False
    assert set(DECISION_SCHEMA["required"]) == set(DECISION_SCHEMA["properties"])


# -- the API call, with a stand-in client ------------------------------------


class FakeMessages:
    def __init__(self, response):
        self.response = response
        self.request = None

    async def create(self, **request):
        self.request = request
        return self.response


def fake_client(stop_reason="end_turn", text=json.dumps(BUG)):
    content = [SimpleNamespace(type="text", text=text)] if text is not None else []
    messages = FakeMessages(SimpleNamespace(stop_reason=stop_reason, content=content))
    return SimpleNamespace(beta=SimpleNamespace(messages=messages)), messages


async def test_claude_decider_sends_a_structured_low_effort_request():
    client, messages = fake_client()
    d = await ClaudeDecider(client, model="claude-opus-5-5").decide(CONTEXT)

    assert d.slug == "save10-negative-total"
    r = messages.request
    assert r["model"] == "claude-opus-5-5"
    assert r["output_config"]["effort"] == "low"
    assert r["output_config"]["format"] == {"type": "json_schema", "schema": DECISION_SCHEMA}
    assert r["fallbacks"] == "default"
    assert "tools" not in r  # the model gets no tools at all


@pytest.mark.parametrize(
    "stop_reason, text",
    [("refusal", None), ("max_tokens", '{"kind": "bu'), ("end_turn", None), ("end_turn", "not json")],
)
async def test_unusable_responses_raise(stop_reason, text):
    client, _ = fake_client(stop_reason, text)
    with pytest.raises(TriageUnavailable):
        await ClaudeDecider(client, model="m").decide(CONTEXT)
