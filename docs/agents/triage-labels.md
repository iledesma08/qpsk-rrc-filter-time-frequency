# Triage Labels

Skills speak in terms of five canonical triage roles. This table maps them to the actual label strings in this repo.

| Label in mattpocock/skills | Label in our tracker | Meaning                                  |
| -------------------------- | -------------------- | ---------------------------------------- |
| `needs-triage`             | `needs-triage`       | This issue still needs evaluation        |
| `needs-info`               | `needs-info`         | Waiting on the reporter for more info    |
| `ready-for-agent`          | `ready-for-agent`    | Fully specified, ready for an AFK agent  |
| `ready-for-human`          | `ready-for-human`    | Requires human implementation (RTL/HW)   |
| `wontfix`                  | `wontfix`            | Will not be done                         |

When a skill mentions a role (e.g. "apply the AFK-ready label"), use the matching string from this table.

Suggested flow for this 4-person team:

1. Every new issue is born with `needs-triage`.
2. At weekly triage (15 min): → `needs-info` (missing data), `wontfix` (out of scope), or `ready-for-agent` / `ready-for-human` (ready, with acceptance criteria).
3. Only work on `ready-*` issues with an assignee.

Create the labels once with `bash scripts/setup-labels.sh`.
