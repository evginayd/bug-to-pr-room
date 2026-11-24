from typing import Any

import pytest

from triager.agent import FALLBACK_REPLY, TeamConfig, Triager
from triager.decision import InvalidDecision, TriageDecision
from triager.state import Stage, Store
from triager.switch_client import Event

INTAKE = "intake-room"
WORK = "work-room"
PR = "https://github.com/evginayd/bug-to-pr-room/pull/6"


class FakeSwitch:
    """Records operations; answers the few that return something."""

    def __init__(self, known_issues: str | None = None, templates=None):
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.known_issues = known_issues
        self.templates = templates if templates is not None else [{"id": "t1", "name": "Bug Work Room"}]

    async def call(self, operation: str, **args: Any) -> Any:
        self.calls.append((operation, args))
        if operation == "list_references":
            docs = [] if self.known_issues is None else [{"id": "d1", "description": "Known issues: fixed bugs"}]
            return {"documents": docs}
        if operation == "load_internal_documents":
            return [{"id": "d1", "content": self.known_issues}]
        if operation == "list_templates":
            return self.templates
        if operation == "run_template":
            return {"room_id": WORK, "room_name": "bug-x"}
        return {}

    def ops(self, name: str) -> list[dict[str, Any]]:
        return [args for op, args in self.calls if op == name]

    def posted(self) -> list[str]:
        return [args["body"] for args in self.ops("post_message")]


class FakeDecider:
    def __init__(self, *decisions):
        self.decisions = list(decisions)
        self.contexts = []

    async def decide(self, context):
        self.contexts.append(context)
        d = self.decisions.pop(0)
        if isinstance(d, Exception):
            raise d
        return d


BUG = TriageDecision(
    kind="bug", severity="high", slug="discount-twice", summary="POST /discount twice applies twice",
    reply="A developer and two agents are on it.",
)


def message(body, *, room=INTAKE, mid="m1", thread=None, sender="zeynep", addressed=True):
    return Event(
        type="message",
        data={"room_id": room, "payload": {"message_id": mid, "thread_id": thread, "body": body,
                                           "sender_name": sender, "addressed": addressed}},
    )


def make(decider, switch=None):
    switch = switch or FakeSwitch()
    store = Store()
    triager = Triager(switch, decider, store, TeamConfig("shop", INTAKE), rules=["rule"])
    return triager, switch, store


async def test_a_bug_gets_a_work_room_and_the_reporter_hears_back():
    triager, switch, store = make(FakeDecider(BUG))
    await triager.handle(message("@shop-triager the discount went on twice"))

    [run] = switch.ops("run_template")
    assert run["template_id"] == "t1"
    assert run["inputs"]["slug"] == "discount-twice"
    assert run["inputs"]["details"] == "the discount went on twice"  # mention stripped
    assert run["inputs"]["intake"] == f"room {INTAKE}, thread m1"
    assert switch.ops("post_message") == [{"body": BUG.reply, "thread_id": "m1"}]
    report = store.get("m1")
    assert (report.stage, report.work_room_id) == (Stage.ROOM_OPEN, WORK)


async def test_unclear_asks_once_then_decides_with_the_answers():
    unclear = TriageDecision(kind="unclear", reply="Quick questions:", questions=["Which code?", "How many times?"])
    decider = FakeDecider(unclear, BUG)
    triager, switch, store = make(decider)

    await triager.handle(message("discount is weird"))
    assert switch.posted() == ["Quick questions:\n1. Which code?\n2. How many times?"]
    assert store.get("m1").stage is Stage.AWAITING_ANSWERS

    await triager.handle(message("SAVE10, three times", mid="m2", thread="m1"))
    second = decider.contexts[1]
    assert second.messages == ["discount is weird", "SAVE10, three times"]
    assert second.questions_allowed is False
    assert store.get("m1").stage is Stage.ROOM_OPEN


async def test_a_known_bug_is_answered_with_the_existing_fix():
    dup = TriageDecision(kind="bug", reply=f"Already fixed: {PR}", duplicate_of=PR)
    switch = FakeSwitch(known_issues=f"- 2026-11-06 | discount twice | {PR}")
    decider = FakeDecider(dup)
    triager, switch, store = make(decider, switch)

    await triager.handle(message("discount applied twice again"))

    assert PR in decider.contexts[0].known_issues
    assert switch.ops("run_template") == []
    assert store.get("m1").stage is Stage.DUPLICATE


async def test_a_question_is_answered_in_the_thread():
    q = TriageDecision(kind="question", reply="SAVE10 takes 10% off.")
    triager, switch, store = make(FakeDecider(q))
    await triager.handle(message("how much is SAVE10?"))

    assert switch.posted() == ["SAVE10 takes 10% off."]
    assert store.get("m1").stage is Stage.ANSWERED


@pytest.mark.parametrize("failure", [InvalidDecision("bad"), None])
async def test_failures_reach_the_reporter_instead_of_silence(failure):
    switch = FakeSwitch(templates=[])  # no template saved: opening the room fails
    triager, switch, store = make(FakeDecider(failure or BUG), switch)
    await triager.handle(message("something broke"))

    assert switch.posted() == [FALLBACK_REPLY]
    assert store.get("m1").stage is Stage.ANSWERED


async def test_the_fixers_hand_back_closes_the_loop():
    triager, switch, store = make(FakeDecider(BUG))
    await triager.handle(message("discount went on twice"))
    switch.calls.clear()

    await triager.handle(message(
        f"@shop-triager PR is open: {PR}. Applying the same discount twice is now refused.",
        room=WORK, mid="m9", sender="shop-fixer",
    ))

    assert switch.ops("connect_to_room") == []  # already connected to the intake room
    [reply] = switch.posted()
    assert "fixed" in reply and PR in reply and "now refused" in reply
    [doc] = switch.ops("create_room_document")
    assert doc["name"] == "Known issues" and PR in doc["content"]
    assert store.get("m1").stage is Stage.FIXED


async def test_known_issues_grows_when_it_exists():
    switch = FakeSwitch(known_issues="- old line")
    triager, switch, store = make(FakeDecider(BUG), switch)
    await triager.handle(message("discount went on twice"))
    await triager.handle(message(f"done: {PR}", room=WORK, mid="m9", sender="shop-fixer"))

    [update] = switch.ops("update_room_document")
    assert update["document_id"] == "d1"
    assert update["content"].startswith("- old line\n- ")


async def test_only_the_fixer_can_close_a_bug():
    triager, switch, store = make(FakeDecider(BUG))
    await triager.handle(message("discount went on twice"))
    await triager.handle(message(f"merged it: {PR}", room=WORK, mid="m9", sender="mallory"))

    assert store.get("m1").stage is Stage.ROOM_OPEN


async def test_replayed_and_unaddressed_messages_are_ignored():
    decider = FakeDecider(BUG)
    triager, switch, store = make(decider)
    await triager.handle(message("discount went on twice"))
    await triager.handle(message("discount went on twice"))  # same id after a reconnect
    await triager.handle(message("chatter", mid="m5", addressed=False))

    assert len(decider.contexts) == 1
    assert len(switch.ops("run_template")) == 1
