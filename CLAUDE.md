# Working on this repo

- Every fix or feature updates the docs in the same commit: `README.md` (Status table, and any section that describes the changed behaviour), `docs/architecture.md` (components, flow, design), `docs/how-it-works.md` (what requesters and the Data Team see) and `docs/phases.md` (a dated entry with what was checked and what is still ⬜).
- Run `python -m pytest -q tests` before pushing (CI runs it too), and add or update a test with every fix or feature; tests stay offline (`tests/fixtures` instead of the platform repos, fakes instead of the web).
- One branch and one pull request per change, from the latest `main`. Merged branches are deleted by `.github/workflows/delete-merged-branch.yml`.
- Everything is in English (UI, questions, User Story, docs, code); the agent still understands Vietnamese answers.
