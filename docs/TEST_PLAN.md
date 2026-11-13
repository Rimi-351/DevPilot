# DevPilot QA Test Plan

## Scope

This plan covers API status codes and authentication boundaries, project and document lifecycle, search and grounded RAG, adversarial request handling, and browser UI endpoint health. It documents the current automated suite and adds a manual execution record format; it does not claim unrun outcomes.

## Test levels

- **Unit:** retrieval, ranking, chunking, schema boundaries, and citation guardrails.
- **Async API integration:** FastAPI endpoints exercised with `httpx.AsyncClient`, async SQLAlchemy, and isolated in-memory SQLite fixtures.
- **Adversarial:** direct and indirect prompt injection, prompt extraction, cross-tenant BOLA, oversized input, and malformed Unicode against the RAG endpoint.
- **Selenium UI:** opt-in Chrome headless smoke checks for `/ui`, invalid-key feedback, upload state, and browser access to `/api/v1/health`. Run with `.venv\Scripts\python -m pytest -m ui -v`.

## Environments

- **Local automated default:** SQLite in-memory database with mocked embeddings and LLM (`TESTING=true`, `EMBEDDING_MOCK=true`, `LLM_MOCK=true`). The pytest default excludes tests marked `ui`.
- **Selenium UI:** local SQLite file, an isolated local Uvicorn process, mocked inference, and `DEMO_MODE=false` so the `devpilot-demo-key` fixture key has ordinary write access for the upload scenario. Requires Chrome/ChromeDriver support through Selenium Manager.
- **PostgreSQL:** production-like integration target using the configured PostgreSQL async URL and migrations. This environment was not available for this local run.

## Entry criteria

- Install `requirements-dev.txt` into the project virtual environment.
- Configure a valid boolean `DEBUG` value and a reachable test database.
- Set `TESTING=true`, `EMBEDDING_MOCK=true`, and `LLM_MOCK=true` for deterministic API integration checks.
- For UI runs, install Chrome and allow Selenium Manager to locate a compatible driver.

## Exit criteria

- Default suite: no unexpected failed or errored tests; each expected failure is tied to a documented defect and reported with the exact counts.
- UI suite: all four UI scenarios pass, or environmental blockers are recorded with exact diagnostics.
- Ruff reports no issues in the requested source, test, and script paths.
- No defect is recorded as fixed unless its regression is verified.

## Risks and limitations

- Mock embeddings are deterministic substitutes and do not measure semantic retrieval quality.
- Mock LLM output cannot establish resistance of a live model/provider to prompt injection or prompt extraction.
- SQLite does not reproduce PostgreSQL locking, query planning, or all type semantics.
- Selenium checks only the explicitly exercised DOM interactions and browser-visible responses; they do not replace accessibility, cross-browser, or load testing.
- Async upload processing can complete as a background task; UI success proves upload acceptance and response rendering, not production queue durability.
