# 2. Demo script: the happy path

About 20 minutes for parts A–D, plus 10 for the optional part E. One request goes from the first message to the approved User Story. Everything shown comes from the real platform repos; there is no demo data.

**The request:** the sales team needs the current CRM customers for a weekly dashboard. The platform already has a dbt model for it (`crm_customers_current`), so the agent should recommend reusing it and propose no new ingestion.

Windows: **R** = requester (normal window), **D** = Data Team (private window), **T** = Teams channel.

Dates assume the demo runs on 2026-10-27. On a later day, move every date so the go-live dates stay in the future.

---

## Opening (1 min)

> "A data request today is a Teams message, a few rounds of questions, someone checking both repos, then a User Story written by hand. The agent does the questions, the repo check and the first draft. People still approve twice: the requester approves the draft, then the Data Team approves the request."

Show the **R** window: the welcome text and the three examples.

---

## Part A: the requester describes the need (≈ 5 min)

| # | Window | Do | What should happen | Say |
|---|---|---|---|---|
| A1 | R | Click the example **📇 Current CRM customers for a dashboard** | The message is sent: *"The sales team needs the current list of CRM customers with their segment for a weekly dashboard."* The step tracker moves to **Details**. The **Your request** card on the right already has: what, source `crm`, refresh `weekly` | "It takes what it can from free text: the source and the refresh were in the sentence." |
| A2 | R | Read the agent's questions | At most **3** missing details are asked, numbered (date range, go-live, grain). If it also asks for the source, answer `source: crm` in the next step | "It never asks more than 3 things at once." |
| A3 | R | Answer (Shift+Enter between lines):<br>`date range: 2024-01-01 to now`<br>`eta: in 4 weeks`<br>`grain: one row per customer` | The card fills in. The agent confirms the date it computed for "in 4 weeks" (2026-11-24) and asks the last missing detail: who uses it | "Labelled or numbered answers both work, and relative dates are converted and confirmed." |
| A4 | R | `used by: Sales team, Power BI weekly dashboard` | All 7 details known. While it works, the bubble shows *Searching the dbt models… / Checking feasibility…*. Then the step tracker moves to **Draft** | "That's 3 turns. The target is 5 or fewer." |

✅ Success criterion 1: the number of turns is ≤ 5. Note it in [03_results.md](03_results.md).

---

## Part B: the requester checks the draft (≈ 4 min)

| # | Window | Do | What should happen | Say |
|---|---|---|---|---|
| B1 | R | Read the **Draft** on the right: user story, acceptance criteria, description. Open **Technical details** | Feasibility **Feasible** (or *Feasible with risks*), recommendation **Existing dbt model `crm_customers_current`**, with the file it was found in. No new ingestion job | "It looked in both repos and found the model already exists, so nothing new is built. Every recommendation names the file it came from." |
| B2 | T | Show the channel | **Nothing yet**. The Data Team hasn't been told | "Nothing goes to the Data Team until the requester approves." |
| B3 | R | Type a change: `eta: 2026-12-01` | A new draft with go-live 2026-12-01, feasibility re-checked | "The requester can still fix things, for free: nothing was sent." |
| B4 | R | Click **✓ Approve draft** | *"Your request is with the Data Team for review"*. Step tracker: **Review**. `outputs/<request_id>/request.json` is written | |
| B5 | T | Show the channel | Card **"[REQ-…] New data request"**: the 7 details, feasibility, "waiting for Data Team review" | "The Data Team gets one card per request, with the request ID in the title." |

---

## Part C: the Data Team reviews (≈ 5 min)

| # | Window | Do | What should happen | Say |
|---|---|---|---|---|
| C1 | D | **🛡 Data Team review → ↻ Refresh**, pick the request in **Waiting for review** | The request card, the feasibility check per source with its file, the risks | "The reviewer sees the same evidence the agent used." |
| C2 | D | Type the comment `change eta to 2026-12-15`, click **✎ Request changes** | The request leaves the queue | "The reviewer can push back. Let's say the team can't do it by December 1st." |
| C3 | R | Watch the requester window (it checks every 5 seconds) | *"The Data Team updated your request: …"* and a **new draft** with go-live 2026-12-15 | "The requester sees the change and approves it again: nobody's request is changed behind their back." |
| C4 | R | Click **✓ Approve draft** | Back to **Review**. No second "New data request" card in Teams (it's sent once per request) | |
| C5 | D | **↻ Refresh**, pick the request again, click **✓ Approve** | *Drafting the User Story… / Sending the summary…* | |

---

## Part D: the User Story (≈ 5 min)

| # | Window | Do | What should happen | Say |
|---|---|---|---|---|
| D1 | R | The requester's page | *"✅ The Data Team approved…"*, the User Story preview, **⬇ User Story** and **⬇ Summary** downloads. Step tracker: **Done** | |
| D2 | T | Show the channel | Card **"[REQ-…] Request approved — User Story ready"**: title, request, feasibility, recommendation `crm_customers_current`, number of risks, the User Story path | |
| D3 | Terminal | `ls outputs/<request_id>/` and `cat outputs/<request_id>/user_story.md` | `request.json`, `feasibility.json`, `user_story.md`, `summary.md`. **No** `teams_messages.jsonl` | "This is the deliverable. Read it as if it landed in your backlog today." |
| D4 | Terminal | `docker exec -it data-onboarding-postgres psql -U agent -d onboarding_agent -c "SELECT request_id, requested_by, status, reviewed_by, review_action FROM sessions ORDER BY created_at DESC LIMIT 1;"` | `status = done`, `requested_by = demo.requester@gmail.com`, `reviewed_by = data.team@gmail.com`, `review_action = approve` | "Sessions survive a restart: they're in PostgreSQL, next to Airflow's metadata database." |
| D5 | Everyone | **Ask the team to rate the User Story** | | "Usable as is, usable with minor edits, major edits, or unusable? And what would you change?" |

✅ Success criteria 2 (existing data recognized) and 3 (rating). Write both down in [03_results.md](03_results.md).

---

## Part E (optional): a source the platform can't onboard yet (≈ 10 min)

Shows the gap path, the "Where does it come from?" question and the web research. Click **＋ New request** in **R** first.

| # | Window | Do | What should happen |
|---|---|---|---|
| E1 | R | `We need Google Search Console clicks and impressions per page for the SEO dashboard.` | The agent asks for the missing details, including **which dataset or product** it is (it only recognizes onboarded systems in free text) |
| E2 | R | Answer with labels: `source: Google Search Console` / `date range: 2025-01-01 to now` / `eta: 2026-12-31` (and any other detail it asked for) | The source name is clean, **Google Search Console**. The next question, asked on its own: **"Where does Google Search Console come from?"** |
| E2b | R | `Google, the Search Console API. Docs: https://developers.google.com/webmaster-tools` | Then the remaining details. Answer: `refresh: daily` / `grain: date x page` / `used by: SEO team, Looker Studio dashboard` |
| E3 | R | Read the gap | *"I checked feasibility and found the following issue(s)…"*: the platform has no template for it. Reply `ok` |
| E4 | R | Wait (up to ~3 min) | *Researching the web docs…*. Then a draft whose **Technical details → Web research** lists the queries, kept results (not `0 / 0` or `0 / 7`), the top 5 links and questions for the Data Team, all marked **unverified** |
| E5 | R → D | **✓ Approve draft**, then approve in **D** | The summary card in Teams has the questions for the Data Team and the links |

Say: *"The agent never pretends it can onboard this: the source stays 'Needs investigation', and the research gives the Data Team a head start, marked unverified."*

If the searches come back empty, show the ready-made search link instead and note it in [03_results.md](03_results.md). Afterwards, check `docker compose -f infrastructure/non-prod/docker-compose.yml logs searxng`.

Other examples, if there's time (show the draft only, no need to approve):

| Example | Expected recommendation |
|---|---|
| **🏷️ CRM segments (not ingested yet)** | CRM is onboarded but `segments` has no job: a **new ingestion job** on `crm-sqlserver-nonprod`, then dbt models |
| **🗄️ HR employees on SQL Server (new system)** | Not onboarded, but SQL Server is supported: a **new connection** from the `sqlserver` template, a job, dbt models |

---

## Close (1 min)

> "That's the prototype: the agent asks the questions, checks both repos and drafts the User Story, and people approve at each step. To close the prototype we need your rating, and a check on 3–5 real past requests. Next: move to VM 1, then 3 User Stories per request (spike, ingestion, transformation)."

Go to [03_results.md](03_results.md).
