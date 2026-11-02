# Working on this repo

- Every fix or feature updates the docs in the same commit: `README.md` (Status table, and any section that describes the changed behaviour), `docs/architecture.md` (components, flow, design), `docs/how-it-works.md` (what requesters and the Data Team see) and `docs/phases.md` (a dated entry with what was checked and what is still ⬜).
- Run `python -m pytest -q tests` before pushing (CI runs it too), and add or update a test with every fix or feature; tests stay offline (`tests/fixtures` instead of the platform repos, fakes instead of the web).
- One branch and one pull request per change, from the latest `main`. Merged branches are deleted by `.github/workflows/delete-merged-branch.yml`.
- Comments say why, not what the next line does. A module starts with a docstring; a public function gets a one- or two-line docstring when its name and types don't tell the whole story (what it returns, when it raises, what it changes), always from about 15 lines. No commented-out code.
- When a change makes a function, file or setting unused, delete it in the same commit, with its tests and docs. `vulture` fails CI on unused code; if something is used from outside what it reads (a notebook, a framework), add the name to `ignore_names` in `pyproject.toml` with a comment saying who uses it.
- Everything is in English (UI, questions, User Story, docs, code); the agent still understands Vietnamese answers.
