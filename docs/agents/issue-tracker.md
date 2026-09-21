# Issue tracker: GitHub

Issues and specs for this repo live as GitHub issues. Use the `gh` CLI for everything.

## Conventions

- **Create an issue**: `gh issue create --title "..." --body "..."`. Use a heredoc for long bodies.
- **Read an issue**: `gh issue view <number> --comments`. Filter comments and labels with `--json`.
- **List**: `gh issue list --state open --json number,title,labels --jq '...'` with `--label` and `--state` filters as needed.
- **Comment**: `gh issue comment <number> --body "..."`
- **Labels**: `gh issue edit <number> --add-label "..."` / `--remove-label "..."`
- **Close**: `gh issue close <number> --comment "..."`

The repo is inferred from `git remote -v`; `gh` does it automatically when run inside the clone (`iledesma08/qpsk-rrc-filter-time-frequency`).

## Pull requests as a triage surface

**PRs as a request surface: no.** _(Set to `yes` if external PRs are accepted as feature requests; `/triage` reads this flag.)_

GitHub shares one number space for issues and PRs, so a bare `#42` may be either: resolve with `gh pr view 42` and fall back to `gh issue view 42`.

## When a skill says "publish to the issue tracker"

Create a GitHub issue with `gh issue create`.

## When a skill says "fetch the relevant ticket"

Run `gh issue view <number> --comments`.

## Wayfinding operations

Used by `/wayfinder`. The **map** is an issue with **sub-issues** as tickets.

- **Map**: an issue labelled `wayfinder:map` (Destination / Notes / Decisions / Fog). `gh issue create --label wayfinder:map`.
- **Child ticket**: an issue linked to the map as a GitHub sub-issue (`gh api` on the sub-issues endpoint). Where sub-issues aren't enabled, add the child to a task list in the map body and put `Part of #<map>` at the top of the child body. Labels: `wayfinder:<type>` (`research`/`prototype`/`grilling`/`task`). When claiming a ticket, self-assign.
- **Blocking**: native GitHub issue dependencies (canonical, UI-visible representation). Where unavailable, use a `Blocked by: #<n>, #<n>` line at the top of the body. A ticket is unblocked when all its blockers are closed.
- **Frontier**: the map's open children with no open blockers and no assignee; first in map order wins.
- **Claim**: `gh issue edit <n> --add-assignee @me`, the session's first write.
- **Resolve**: `gh issue comment <n> --body "<answer>"`, then `gh issue close <n>`, then append a context pointer (gist + link) to the map's Decisions.
