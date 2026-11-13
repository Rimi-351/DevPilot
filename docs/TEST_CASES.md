# Manual Test Cases

| ID | Module | Precondition | Steps | Expected Result | Actual Result | Status |
|---|---|---|---|---|---|---|
| TC-01 | Health | Service is running | GET `/api/v1/health` | HTTP 200 and healthy status | Not Executed | Not Executed |
| TC-02 | Authentication | No API key | GET `/api/v1/projects` without header | HTTP 401 | Not Executed | Not Executed |
| TC-03 | Authentication | Service is running | GET projects with an unknown non-empty API key | HTTP 401 because the key was not issued to a tenant | Not Executed | Not Executed |
| TC-04 | Tenant isolation | Tenant A and B projects exist | Tenant A requests Tenant B project | HTTP 403 | Not Executed | Not Executed |
| TC-05 | Projects | Authenticated key | POST a valid project payload | HTTP 201 and owner is caller | Not Executed | Not Executed |
| TC-06 | Projects | Caller owns project | GET project by ID | HTTP 200 with matching project | Not Executed | Not Executed |
| TC-07 | Projects | Caller owns project | PATCH project name | HTTP 200 and updated name | Not Executed | Not Executed |
| TC-08 | Projects | Caller owns project | DELETE project | HTTP 204 and subsequent lookup is absent | Not Executed | Not Executed |
| TC-09 | Documents | Caller owns a project | Upload a supported `.txt` file | HTTP 201 with document and job identifiers | Not Executed | Not Executed |
| TC-10 | Documents | Document exists | List documents filtered by project | HTTP 200 and uploaded document is listed | Not Executed | Not Executed |
| TC-11 | Documents | Caller owns a project | Upload unsupported extension | HTTP 400 with validation detail | Not Executed | Not Executed |
| TC-12 | Documents | Caller owns a project | Upload file over configured size limit | HTTP 413 | Not Executed | Not Executed |
| TC-13 | Search | Project has indexed content | POST hybrid search with relevant query | HTTP 200 and ranked results | Not Executed | Not Executed |
| TC-14 | RAG | Project has indexed content | Ask a question supported by a document | HTTP 200 with answer and valid citations | Not Executed | Not Executed |
| TC-15 | RAG guardrail | Project has unrelated content | Ask for unavailable facts | HTTP 200 with grounded rejection and no citations | Not Executed | Not Executed |
| TC-16 | Adversarial | Project exists | Submit direct prompt injection in query | No secret or system prompt disclosure; response follows implemented guardrails | Not Executed | Not Executed |
| TC-17 | Adversarial | Project exists | Submit oversized and zero-width Unicode queries | Controlled HTTP response; no unhandled server error | Not Executed | Not Executed |
| TC-18 | UI | Chrome and Selenium available | Open `/ui`, configure key, upload sample text, request health | Correct title/heading, visible auth/upload states, healthy JSON | Not Executed | Not Executed |
