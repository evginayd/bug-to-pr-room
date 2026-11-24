"""Where each report stands. Filled in at milestone 3; the states are fixed now.

    NEW -> AWAITING_ANSWERS -> ROOM_OPEN -> FIXED
    NEW -> ANSWERED     (a question or a feature request)
    NEW -> DUPLICATE    (already known; the reporter gets the existing link)

AWAITING_ANSWERS can be entered once per report, which is how the "at most
two questions" rule is enforced in code rather than in the prompt.
"""

from __future__ import annotations

from enum import Enum


class Stage(str, Enum):
    NEW = "new"
    AWAITING_ANSWERS = "awaiting_answers"
    ROOM_OPEN = "room_open"
    FIXED = "fixed"
    ANSWERED = "answered"
    DUPLICATE = "duplicate"


TRANSITIONS: dict[Stage, set[Stage]] = {
    Stage.NEW: {Stage.AWAITING_ANSWERS, Stage.ROOM_OPEN, Stage.ANSWERED, Stage.DUPLICATE},
    Stage.AWAITING_ANSWERS: {Stage.ROOM_OPEN, Stage.ANSWERED, Stage.DUPLICATE},
    Stage.ROOM_OPEN: {Stage.FIXED},
    Stage.FIXED: set(),
    Stage.ANSWERED: set(),
    Stage.DUPLICATE: set(),
}

MAX_QUESTIONS = 2


def can_move(current: Stage, target: Stage) -> bool:
    return target in TRANSITIONS[current]
