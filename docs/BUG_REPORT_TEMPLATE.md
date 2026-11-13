# Bug Report Template

- **Title:**
- **Severity:** Critical / High / Medium / Low
- **Priority:** P0 / P1 / P2 / P3
- **Environment:**
- **Preconditions:**
- **Steps to Reproduce:**
  1.
- **Expected Result:**
- **Actual Result:**
- **Evidence:** logs, screenshots, request/response, or test output

## Discovered Defects & Weaknesses

### RAG query has no maximum length

- **Location:** [src/schemas/rag.py](/E:/Projects/Devpilot/src/schemas/rag.py:11)
- **Evidence:** `RagQueryRequest.query` specifies `min_length=1` but no `max_length`. `test_oversized_and_zero_width_unicode_queries_are_handled` sends a 180 KB query; the endpoint accepts it (HTTP 200) instead of rejecting it (HTTP 422), so the strict regression expectation is marked `xfail`.
- **Reproduction:** Create a project, then POST `/api/v1/projects/{project_id}/rag` with JSON `{"query":"oversized oversized ..."}` containing 20,000 repetitions of `oversized `.
- **Risk:** Requests can carry arbitrarily large query strings into application processing and response serialization. No production impact was measured.

### Unknown non-empty API keys are treated as authenticated tenant identities

- **Location:** [src/core/security.py](/E:/Projects/Devpilot/src/core/security.py:59)
- **Evidence:** `get_current_api_key` rejects only missing or whitespace-only headers, then returns every other string. The `test_unknown_nonempty_api_key_is_rejected` regression check is marked `xfail` because an unknown key receives HTTP 200 from the projects list instead of HTTP 401. The UI connection test dynamically marks the same discrepancy `xfail` after observing it.
- **Reproduction:** GET `/api/v1/projects` with `X-API-Key: unknown-unissued-key`; the response is HTTP 200 with an empty tenant project list.
- **Risk:** There is no server-side registry or signature validation for issued credentials. The API effectively lets any caller create a self-selected tenant identity; tenant data with a different key remains subject to object-level ownership checks.

## Verification Limitations

The API adversarial checks use mocked LLM and embedding services. They verify route behavior and deterministic guardrails but cannot establish how a live model responds to prompt injection or system prompt extraction. The initial test command also depended on inherited shell configuration (`DEBUG=release`) and the host's inaccessible default pytest temp directory; verification used `DEBUG=false` and a workspace temp directory.
