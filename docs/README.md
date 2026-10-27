# Docs

| Doc | Read it when you want to know… |
|---|---|
| [HOW_IT_WORKS.md](HOW_IT_WORKS.md) | what happens to a data request from the first message to the User Story, for the requester and for the Data Team |
| [ARCHITECTURE.md](ARCHITECTURE.md) | how the system is built: components, the agent graph, state, the two repos it reads, LLM, storage, integrations, deployment |
| [PHASES.md](PHASES.md) | what was built in each phase, what is verified and what isn't, known issues and next steps |
| [prototype_demo/](prototype_demo/README.md) | how to run the team demo that closes the prototype: preparation, the happy-path script click by click, the results sheet and past-request template |
| [POSTGRESQL.md](POSTGRESQL.md) | where the agent's data is stored (PostgreSQL, next to Airflow's metadata DB), how to check every table at a glance, and the queries to check them after a demo |

Other docs in the repo:

| Doc | About |
|---|---|
| [../README.md](../README.md) | Quick start, configuration (env vars), Colab model hosting, which repos the agent reads |
| [../PLAN.md](../PLAN.md) | The original prototype plan: goals, phases, success criteria, out of scope |
| [../infrastructure/README.md](../infrastructure/README.md) | Running the app with Docker: laptop, VM, GitHub Codespaces |
| [data-onboarding-ingestion](https://github.com/thanhphat2609/data-onboarding-ingestion) | Source templates, connections and jobs the agent reads |
| [data-onboarding-transformation](https://github.com/thanhphat2609/data-onboarding-transformation) | dbt models the agent reads |

Keep these docs current: when a phase item changes status, update [PHASES.md](PHASES.md). When a node, the state or the UI flow changes, update [ARCHITECTURE.md](ARCHITECTURE.md) and [HOW_IT_WORKS.md](HOW_IT_WORKS.md).
