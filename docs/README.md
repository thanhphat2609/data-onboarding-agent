# Docs

| Doc | Read it when you want to know… |
|---|---|
| [how-it-works.md](how-it-works.md) | what happens to a data request from the first message to the User Story, for the requester and for the Data Team |
| [architecture.md](architecture.md) | how the system is built: components, the agent graph, state, the two repos it reads, LLM, storage, integrations, deployment |
| [phases.md](phases.md) | what was built in each phase, what is verified and what isn't, known issues and next steps |
| [prototype_demo/](prototype_demo/README.md) | how to run the team demo that closes the prototype: preparation, the happy-path script click by click, the results sheet and past-request template |
| [postgresql.md](postgresql.md) | where the agent's data is stored (PostgreSQL, next to Airflow's metadata DB), how to check every table at a glance, and the queries to check them after a demo |

Other docs in the repo:

| Doc | About |
|---|---|
| [../README.md](../README.md) | Quick start, configuration (env vars), Colab model hosting, which repos the agent reads |
| [plan.md](plan.md) | The original prototype plan: goals, phases, success criteria, out of scope |
| [../infrastructure/README.md](../infrastructure/README.md) | Running the app with Docker: laptop, VM, GitHub Codespaces |
| [data-onboarding-ingestion](https://github.com/thanhphat2609/data-onboarding-ingestion) | Source templates, connections and jobs the agent reads |
| [data-onboarding-transformation](https://github.com/thanhphat2609/data-onboarding-transformation) | dbt models the agent reads |

Keep these docs current: when a phase item changes status, update [phases.md](phases.md). When a node, the state or the UI flow changes, update [architecture.md](architecture.md) and [how-it-works.md](how-it-works.md).
