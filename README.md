# Bug-to-PR Room

> Report a bug in plain words in your team chat. Three AI agents reproduce it, fix it and ask you before anything ships.

Built for the [Flip the Switch hackathon](https://www.wemakedevs.org/hackathons/switch) (Track 1: Best Business Workflow).

**Demo video:** _TODO: link_

## The problem

A bug report in a team chat usually starts a slow relay: someone asks for details, someone else tries to reproduce it, a developer finally fixes it, and the context is scattered across threads and tickets. AI coding agents can do much of this work, but on their own they sit in one person's terminal, out of sight of the team.

## What it does

The `#shop-bugs` room is a channel in the team's chat where people and agents work the same bug in the same thread:

1. **A person** reports a bug in plain language.
2. **Triager** restates it in API terms, classifies it, gives it a severity, opens a task in the room and hands it to Repro. If details are missing, it asks the reporter.
3. **Repro** writes the smallest failing pytest test, runs it and posts the exact output.
4. **Fixer** adds that test, makes the smallest fix, runs the whole suite and asks the reporter: *"Approve this fix?"*
5. **The person** approves or pushes back. Only after approval does Fixer push a branch and open the pull request.

```mermaid
flowchart LR
    P([Person]) -->|reports a bug| T[Triager]
    T -->|routes| R[Repro]
    R -->|failing test| F[Fixer]
    F -->|"Approve this fix?"| D{Person approves?}
    D -->|yes| PR[Pull request opened]
    D -->|no, with direction| F
```

### It already works

Two bugs reported in the room in plain words have gone the whole way, each ending in a pull request that Fixer opened only after the reporter approved it in the thread:

| Reported in chat | Pull request opened by Fixer |
|---|---|
| "I put -3 mugs in my cart and the total went negative." | [#1 fix: reject negative quantity on add_item](https://github.com/evginayd/bug-to-pr-room/pull/1) |
| "SAVE10 on a cart with one sticker pack made the total -6.00." | [#3 fix: compute SAVE10 as percentage, not flat amount](https://github.com/evginayd/bug-to-pr-room/pull/3) |

Each pull request carries the regression test Repro wrote, the fix, the result of the whole test suite and the ID of the room thread where it was approved.

## How it uses Switch

Switch is what makes this a team workflow rather than three scripts:

- **One room, shared context.** The chat channel is a Switch room. People and all three agents read the same history, so every hand-off is visible and nothing is re-explained.
- **Agents as teammates.** Each agent joins the channel under its own name and avatar, and they address each other by name to hand work on.
- **Room instructions and rules.** The workflow, the one-bug-per-thread rule and the human approval gate live in the room's instructions, not in code.
- **Addressing.** Anyone in the room can talk to Triager and Fixer; Repro only takes work from the team's own agents.
- **One template.** [`agents/bug-to-pr.template.yaml`](agents/bug-to-pr.template.yaml) creates all three agents and the room in one step from Switch Console.

- **Tasks.** Triager opens a Switch task for every bug before handing it on, so each report is tracked as work with a life of its own rather than one message lost in the scroll.
- **A human gate the whole room can see.** Only a person's reply in the bug's thread counts as an approval, and the room instructions tell every agent that another agent's message never does. The approval, the decision and the pull request link all stay in the room's log next to the report that started it.

```mermaid
flowchart LR
    subgraph Chat["Team chat: Mattermost, Slack, Teams, Discord"]
        CH["shop-bugs channel"]
    end
    subgraph Server["Switch server, in Docker"]
        ROOM["shop-bugs room<br/>shared log, instructions, tasks"]
    end
    subgraph Console["Switch Console, on your machine"]
        T["Triager<br/>Claude Code"]
        R["Repro<br/>Claude Code"]
        F["Fixer<br/>Claude Code"]
    end
    CH <-->|bridge| ROOM
    ROOM <-->|"agent protocol"| T
    ROOM <-->|"agent protocol"| R
    ROOM <-->|"agent protocol"| F
    F -->|"push and open PR,<br/>after approval"| GH[("GitHub fork")]
```

Take Switch away and the three agents are back in three terminals: nobody on the team sees the hand-offs, and nothing stops a fix from shipping without a person saying yes.

## Design choices

- **Three agents, not one.** Splitting the work is what makes the result trustworthy. Repro may not change code or commit, so a reproduction can't quietly turn into a fix. Fixer may not approve its own work, so every change is seen by a person first.
- **Proof before claims.** A room rule says every claim about the code comes with the command that was run and its output. Repro must post a failing test before anything is fixed, and Fixer posts the full test summary before asking for approval.
- **Repro takes work only from agents.** Its addressing is `owner-agents`, so a report can't skip triage and land straight on the reproducer.
- **One clone per agent.** Each agent works in its own directory with its own clone of the repository, so they never trip over each other's working tree.
- **Nothing touches main.** Fixer works on a `fix/<bug>` branch, opens a pull request and stops there. Merging stays a person's job.

## Run it yourself

You need: [Switch Console](https://github.com/sandbox-quantum/switch#getting-started), Docker, Python 3.11+, git, the [GitHub CLI](https://cli.github.com/) signed in (`gh auth login`), and Claude Code (or Codex / OpenCode) signed in.

1. **Fork this repository** so the Fixer can open pull requests on your copy.
2. **Check the demo app** works: `./scripts/setup.sh` (macOS/Linux) or `.\scripts\setup.ps1` (Windows). It creates a virtual environment, installs the app and should end with `10 passed`.
3. **Start Switch:** open Switch Console and start a local server. It comes with Mattermost, so no Slack workspace is needed.
4. **Create the room:** in Console, import `agents/bug-to-pr.template.yaml` as a template and run it. Set `repo_url` to your fork's HTTPS URL.
5. **Report a bug** in the new `#shop-bugs` channel, and **mention `@Triager`** in it: agents only wake when they are addressed. Some to try:
   - "I put -3 mugs in my cart and the total went negative."
   - "SAVE10 on a cart with one sticker pack made the total -6.00."
   - "Removing something that isn't in my cart gives a server error."
   - "I clicked apply on SAVE10 three times and got 30 off."

### Troubleshooting

- **"Could not reach the server … timeout" when creating from the template.** The first run can take longer than Switch Console waits, while the server goes on creating the agents in the background. Wait a minute and check *Your Agents* and *Your Rooms* before retrying; a retry that reports "an agent named shop-triager already exists" means the first run succeeded.
- **Agents answer in a thread.** Open the "replies" under your message to follow the hand-offs.
- **Don't merge the fix PRs** if you want to replay the demo: the bugs in `demo-app` are the scenario.

_TODO: screenshots of each step, listed in [`docs/`](docs/README.md)._

## Repository layout

```
agents/     Switch template: the three agents, the room and its rules
demo-app/   The shop API the agents work on (FastAPI + pytest)
scripts/    Setup helpers for the demo app
docs/       Architecture diagram and screenshots
```

The demo app is deliberately small, with a few realistic bugs in it, so the whole flow runs in minutes and anyone can reproduce the demo.

## Team

Team Craftopiq:

| Name | GitHub |
|---|---|
| Evgin Aydın | [@evginayd](https://github.com/evginayd) |
| Zeynep Aslan | [@zeynepaslann404](https://github.com/zeynepaslann404) |
| Can Turk | [@cantrk21](https://github.com/cantrk21) |

## License

[MIT](LICENSE)
