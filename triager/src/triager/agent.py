"""The Triager: turns room events into decisions and decisions into actions.

Every action is a Switch operation called from here, never by the model:
- a report in the intake room is triaged, and a bug gets its own work room
  from the saved "Bug Work Room" template;
- the Fixer's hand-back in a work room goes back to the reporter's thread and
  into the intake room's Known issues document.

Switch operations act on the room the connection is connected to, so events
are handled one at a time and every action connects to its room first.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol

from .decision import (
    Decider,
    InvalidDecision,
    ReportContext,
    TriageDecision,
    TriageUnavailable,
)
from .state import Report, Stage, Store
from .switch_client import Event

log = logging.getLogger(__name__)

KNOWN_ISSUES = "Known issues"
TEMPLATE = "Bug Work Room"
PR_LINK = re.compile(r"https://github\.com/[\w.-]+/[\w.-]+/pull/\d+")
MENTION = re.compile(r"@[\w-]+\s*")

FALLBACK_REPLY = (
    "Thanks, I've got your report but couldn't sort it out on my own. "
    "A developer will take a look."
)


class Switch(Protocol):
    async def call(self, operation: str, **arguments: Any) -> Any: ...


@dataclass(frozen=True)
class TeamConfig:
    team: str  # prefix of the team's agents, e.g. "shop"
    intake_room_id: str

    @property
    def fixer(self) -> str:
        return f"{self.team}-fixer"


class Triager:
    def __init__(
        self,
        switch: Switch,
        decider: Decider,
        store: Store,
        team: TeamConfig,
        rules: list[str],
    ):
        self.switch = switch
        self.decider = decider
        self.store = store
        self.team = team
        self.rules = rules
        self._connected_to: str | None = None

    # -- events -------------------------------------------------------------

    async def handle(self, event: Event) -> None:
        if event.type != "message":
            return
        p = event.payload
        message_id = p.get("message_id")
        if not p.get("addressed") or not message_id:
            return
        if not self.store.first_time(message_id):
            return  # replayed after a reconnect

        if event.room_id == self.team.intake_room_id:
            await self._on_report(p)
            return
        report = self.store.by_work_room(event.room_id or "")
        if report and p.get("sender_name") == self.team.fixer:
            await self._on_fixer(report, p.get("body", ""))

    # -- intake -------------------------------------------------------------

    async def _on_report(self, p: dict[str, Any]) -> None:
        thread_id = p.get("thread_id") or p["message_id"]
        body = MENTION.sub("", p.get("body", "")).strip()
        report = self.store.get(thread_id)

        if report is None:
            report = Report(
                thread_id=thread_id,
                intake_room_id=self.team.intake_room_id,
                reporter=p.get("sender_name", ""),
                messages=[body],
            )
            self.store.save(report)
        elif report.stage is Stage.AWAITING_ANSWERS:
            report.messages.append(body)
            self.store.save(report)
        else:
            return  # already handled; the work room carries it from here

        try:
            decision = await self.decider.decide(
                ReportContext(
                    messages=report.messages,
                    rules=self.rules,
                    known_issues=(await self._known_issues())[1],
                    questions_allowed=report.questions_allowed,
                )
            )
        except (TriageUnavailable, InvalidDecision) as exc:
            log.warning("no usable decision for %s: %s", thread_id, exc)
            await self._reply(report, FALLBACK_REPLY)
            self.store.move(report, Stage.ANSWERED)
            return

        try:
            await self._act(report, decision)
        except Exception:
            # e.g. the template is missing or refused: tell the reporter rather than go quiet
            log.exception("acting on the decision for %s failed", thread_id)
            await self._reply(report, FALLBACK_REPLY)
            if report.stage is not Stage.ANSWERED:
                self.store.move(report, Stage.ANSWERED)

    async def _act(self, report: Report, d: TriageDecision) -> None:
        if d.duplicate_of:
            await self._reply(report, d.reply)
            self.store.move(report, Stage.DUPLICATE, pr_url=d.duplicate_of)
        elif d.kind == "unclear":
            await self._reply(report, _numbered(d.reply, d.questions))
            self.store.move(report, Stage.AWAITING_ANSWERS)
        elif d.kind == "bug":
            room_id = await self._open_work_room(report, d)
            await self._reply(report, d.reply)
            self.store.move(
                report, Stage.ROOM_OPEN, slug=d.slug, summary=d.summary, work_room_id=room_id
            )
        else:  # question or feature
            await self._reply(report, d.reply)
            self.store.move(report, Stage.ANSWERED)

    async def _open_work_room(self, report: Report, d: TriageDecision) -> str:
        templates = await self.switch.call("list_templates", query=TEMPLATE)
        template = next((t for t in templates if t.get("name") == TEMPLATE), None)
        if template is None:
            raise RuntimeError(f'no saved template named "{TEMPLATE}"')
        result = await self.switch.call(
            "run_template",
            template_id=template["id"],
            inputs={
                "team": self.team.team,
                "slug": d.slug,
                "summary": d.summary,
                "details": "\n\n".join(report.messages),
                "severity": d.severity,
                "intake": f"room {report.intake_room_id}, thread {report.thread_id}",
            },
        )
        return result["room_id"]

    # -- hand-back ----------------------------------------------------------

    async def _on_fixer(self, report: Report, body: str) -> None:
        if report.stage is not Stage.ROOM_OPEN:
            return
        link = PR_LINK.search(body)
        if not link:
            return  # the Fixer is talking to the developer, not handing back
        pr_url = link.group(0)
        # The Fixer ends with one plain sentence for the reporter; keep the
        # sentences that are not about the pull request itself.
        sentences = re.split(r"(?<=[.!?])\s+", MENTION.sub("", body).strip())
        explanation = " ".join(s for s in sentences if not PR_LINK.search(s)).strip()

        reply = "Good news: this is fixed and waiting to ship."
        if explanation:
            reply += f" {explanation}"
        await self._reply(report, f"{reply}\n{pr_url}")
        doc_id, content = await self._known_issues()
        line = f"- {date.today().isoformat()} | {report.summary} | {pr_url}"
        if doc_id:
            await self.switch.call(
                "update_room_document", document_id=doc_id, content=f"{content.rstrip()}\n{line}"
            )
        else:
            await self.switch.call(
                "create_room_document",
                name=KNOWN_ISSUES,
                description=f"{KNOWN_ISSUES}: bugs reported here and fixed, with their pull requests",
                instructions="One line per fixed bug: date | what was wrong | pull request.",
                content=line,
            )
        self.store.move(report, Stage.FIXED, pr_url=pr_url)

    # -- switch helpers -----------------------------------------------------

    async def _connect(self, room_id: str) -> None:
        if self._connected_to != room_id:
            await self.switch.call("connect_to_room", room_id=room_id)
            self._connected_to = room_id

    async def _reply(self, report: Report, body: str) -> None:
        await self._connect(report.intake_room_id)
        await self.switch.call("post_message", body=body, thread_id=report.thread_id)

    async def _known_issues(self) -> tuple[str | None, str]:
        """The Known issues document of the intake room: (id, content), or (None, "")."""
        await self._connect(self.team.intake_room_id)
        refs = await self.switch.call("list_references")
        doc = next((d for d in refs.get("documents", []) if _is_known_issues(d)), None)
        if doc is None:
            return None, ""
        [loaded] = await self.switch.call("load_internal_documents", ids=[doc["id"]])
        return doc["id"], loaded.get("content", "")


def _is_known_issues(doc: dict[str, Any]) -> bool:
    return KNOWN_ISSUES.lower() in (doc.get("name") or doc.get("description") or "").lower()


def _numbered(intro: str, questions: list[str]) -> str:
    lines = [intro] if intro else []
    lines += [f"{i}. {q}" for i, q in enumerate(questions, 1)]
    return "\n".join(lines)
