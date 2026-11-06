# docs

Screenshots used in the README, in `docs/screenshots/`. The architecture diagrams are drawn in Mermaid in the main [README](../README.md#how-it-uses-switch), so they stay in step with the text.

One per step of the flow:

| File | What it shows |
|---|---|
| `01-console-template.png` | Switch Console with `bug-to-pr.template.yaml` imported and its form filled in |
| `02-agents-and-room.png` | *Your Agents* and *Your Rooms* in Console after the template ran |
| `03-report.png` | A person reporting a bug in plain words in `#shop-bugs` and mentioning `@Triager` |
| `04-triage.png` | Triager's questions to the reporter and its note that a work room is open |
| `05-work-room.png` | The `bug-...` room Triager opened, with its kickoff waking Repro |
| `06-repro.png` | Repro's failing test with the pytest output |
| `07-rejection.png` | The developer rejecting Fixer's first fix with direction, and Fixer redoing it |
| `08-approval.png` | Fixer's diff and test summary, "Approve this fix?" and the person's "approved" |
| `09-pull-request.png` | The pull request Fixer opened, with the room named |
| `10-reported-back.png` | Triager's plain-words "it's fixed" reply in the reporter's thread |
| `11-known-issues.png` | The *Known issues* document |
| `12-duplicate.png` | A second report of the same bug, recognised and answered with the PR link |
