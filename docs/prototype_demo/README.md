# Prototype demo

Everything needed to run the team demo and close the prototype phase ([plan.md](../plan.md)).

| Step | File | When | Time |
|---|---|---|---|
| 1 | [01_prepare.md](01_prepare.md) | Before the demo: start the stack, connect Teams, create the accounts, do a dry run | ~45 min |
| 2 | [02_happy_path.md](02_happy_path.md) | The demo script: one request from first message to User Story, click by click, with what to say | ~20 min (+10 optional) |
| 3 | [03_results.md](03_results.md) | During and after the demo: the checklist, the team's ratings, the decision to close the prototype | ~15 min |
| – | [past_requests/](past_requests/) | Before or after the demo: 3–5 real past requests replayed with `python -m agent.workflow.evaluate` | ~1 h to write |

## What the demo has to prove

The prototype is done when the agent does these 3 things on real platform data, and the Data Team agrees ([plan.md → Success criteria](../plan.md#success-criteria)):

| # | The agent… | Shown in |
|---|---|---|
| 1 | collects all 7 details in **≤ 5 turns** for a normal request | Happy path, part A |
| 2 | gets feasibility right: recognizes data that **already exists**, and finds **gaps** (date range, a source the platform can't onboard) | Happy path, parts A and E; past requests |
| 3 | writes a User Story the Data Team rates **"usable, needs only minor edits"** or better | Happy path, part D; [03_results.md](03_results.md) |

Plus the parts the prototype added on the way, shown working end to end in Docker: requester approval of the draft, Data Team review, real Teams cards, PostgreSQL sessions.

## Roles

| Who | Signs in as | Uses |
|---|---|---|
| **Presenter (requester)** | any email, e.g. `demo.requester@gmail.com` (first sign-in sets the password) | 💬 Request, 🗂 Sessions |
| **Data Team reviewer** | `data.team@gmail.com` (from `ACCOUNTS`) | 🛡 Data Team review, ⚙️ Settings |
| **Audience** | – | watches the screen and the Teams channel, rates the User Story |

Two browser windows side by side: a normal one for the requester and a private one for the Data Team. Keep the Teams channel open on a second screen or a phone.
