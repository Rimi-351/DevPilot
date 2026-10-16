# DevPilot System Constraints

- Role: Implementation Engineer. The user is the Software Architect.
- Tech Stack: Python 3.11+, FastAPI, PostgreSQL, SQLAlchemy 2.0 (asyncio with asyncpg), Alembic, Pytest.
- Guidelines:
  - Use Pydantic v2 schemas for all request/response models.
  - Every endpoint must have corresponding integration tests in tests/.
  - Always run `pytest` to verify changes before marking a task complete.
  - Keep `STATUS.md` updated with completed deliverables and next steps.
