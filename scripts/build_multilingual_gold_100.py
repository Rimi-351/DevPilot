"""Script to construct the 100-query multilingual gold-standard benchmark dataset.

Generates benchmarks/multilingual_gold_100.jsonl with:
- 34 English technical queries (system architecture, core specifications)
- 33 Pure Bangla script queries (company policy, native Bengali system features)
- 33 Romanized Banglish queries (code-mixed engineering questions)

Each line conforms strictly to:
{
    "query_id": "q_001",
    "language": "english|bangla|banglish",
    "query": "...",
    "ground_truth_chunk_ids": ["..."],
    "reference_answer": "...",
    "corpus": [...]
}
"""

import asyncio
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.services.embedding import get_embedding_service


# -----------------------------------------------------------------------------
# 1. CORPUS CHUNKS POOL (English, Pure Bangla, Banglish & General Distractors)
# -----------------------------------------------------------------------------
CORPUS_CHUNKS = {
    # --- English Technical Specifications & System Architecture ---
    "chunk_en_config_01": {
        "chunk_id": "chunk_en_config_01",
        "content": "Settings specification: CHUNK_SIZE defaults to 512 characters and CHUNK_OVERLAP defaults to 64 characters in src/core/config.py to standardize text chunking across DevPilot.",
        "filename": "config.md",
    },
    "chunk_en_security_01": {
        "chunk_id": "chunk_en_security_01",
        "content": "Security dependencies in src/core/security.py extract the X-API-Key header, raising HTTP 401 Unauthorized if missing, empty, or whitespace to authenticate callers.",
        "filename": "security.md",
    },
    "chunk_en_tenant_01": {
        "chunk_id": "chunk_en_tenant_01",
        "content": "Cross-tenant project access triggers verify_project_tenant_access and returns HTTP 403 Forbidden whenever an authenticated caller attempts accessing or modifying another tenant's project.",
        "filename": "multitenancy.md",
    },
    "chunk_en_rrf_01": {
        "chunk_id": "chunk_en_rrf_01",
        "content": "Reciprocal Rank Fusion uses constant k=60 to fuse dense and BM25 rank contributions: RRF_score = sum(1.0 / (60 + rank + 1)), ensuring high-confidence matches in either mode rank near the top.",
        "filename": "hybrid_search.md",
    },
    "chunk_en_bm25_01": {
        "chunk_id": "chunk_en_bm25_01",
        "content": "Sparse lexical search utilizes BM25Okapi from the rank-bm25 package to tokenize and score document terms with term frequency and inverse document frequency statistics.",
        "filename": "bm25.md",
    },
    "chunk_en_embedding_01": {
        "chunk_id": "chunk_en_embedding_01",
        "content": "DevPilot vector embeddings default to sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 generating normalized 384-dimensional dense vectors with FastEmbed CPU execution and SentenceTransformers fallback.",
        "filename": "embedding_spec.md",
    },
    "chunk_en_reranker_01": {
        "chunk_id": "chunk_en_reranker_01",
        "content": "The Cross-Encoder Reranker uses cross-encoder/ms-marco-MiniLM-L-6-v2 to evaluate full query-document interaction across top candidates, assigning rerank_score to each item.",
        "filename": "reranker_spec.md",
    },
    "chunk_en_rerank_fallback_01": {
        "chunk_id": "chunk_en_rerank_fallback_01",
        "content": "When transformer models fail to load or are unavailable, RerankerService logs warning 'RERANKER_FALLBACK_ACTIVE' and applies lexical term overlap heuristics with reranker_engine metadata.",
        "filename": "reranker_fallback.md",
    },
    "chunk_en_unsupported_01": {
        "chunk_id": "chunk_en_unsupported_01",
        "content": "The unsupported_claims_rate metric defines a threshold of 0.40 sentence-to-chunk token overlap ratio, flagging sentences below 40% overlap as ungrounded or hallucinated.",
        "filename": "metrics_spec.md",
    },
    "chunk_en_storage_01": {
        "chunk_id": "chunk_en_storage_01",
        "content": "LocalStorageService restricts uploaded files to a maximum size of 10MB (10485760 bytes), rejecting larger files with HTTP 413 and persisting accepted files organized by project ID.",
        "filename": "storage_service.md",
    },
    "chunk_en_job_status_01": {
        "chunk_id": "chunk_en_job_status_01",
        "content": "ProcessingJob status transitions through JobStatus enum: PENDING, IN_PROGRESS, COMPLETED, and FAILED, allowing clients to poll job progress asynchronously.",
        "filename": "jobs_status.md",
    },
    "chunk_en_alembic_01": {
        "chunk_id": "chunk_en_alembic_01",
        "content": "Database migrations manage PostgreSQL schema evolution using command 'alembic upgrade head' to apply migrations auto-generated from SQLAlchemy 2.0 declarative models.",
        "filename": "alembic_migrations.md",
    },
    "chunk_en_storage_hash_01": {
        "chunk_id": "chunk_en_storage_hash_01",
        "content": "LocalStorageService computes a hexadecimal SHA-256 digest over file bytes for content verification and duplicate detection before saving raw bytes to disk.",
        "filename": "storage_hash.md",
    },
    "chunk_en_background_01": {
        "chunk_id": "chunk_en_background_01",
        "content": "Document text extraction and chunk persistence run asynchronously in background tasks via FastAPI BackgroundTasks with an independent DB session so uploads respond immediately.",
        "filename": "background_tasks.md",
    },
    "chunk_en_pdf_01": {
        "chunk_id": "chunk_en_pdf_01",
        "content": "PDF document extraction utilizes pypdf.PdfReader to extract text page-by-page, appending '--- Page N ---' boundary markers and gracefully skipping empty pages.",
        "filename": "pdf_extractor.md",
    },
    "chunk_en_pydantic_01": {
        "chunk_id": "chunk_en_pydantic_01",
        "content": "DevPilot configuration is managed using Pydantic Settings with automatic environment variable loading from .env files, supporting type coercion and runtime validation.",
        "filename": "config_pydantic.md",
    },
    "chunk_en_agent_fsm_01": {
        "chunk_id": "chunk_en_agent_fsm_01",
        "content": "The bounded agent workflow executes a strict 4-phase finite state machine: SEARCH -> INSPECT -> SUMMARIZE -> PROPOSE, preventing invalid phase progression or backwards regression.",
        "filename": "agent_workflow.md",
    },
    "chunk_en_agent_firewall_01": {
        "chunk_id": "chunk_en_agent_firewall_01",
        "content": "GuardedToolDispatcher enforces a Pydantic ingress validation firewall: any malformed tool input returns ToolExecutionStatus.VALIDATION_ERROR to prompt agent self-correction.",
        "filename": "agent_firewall.md",
    },
    "chunk_en_agent_timeout_01": {
        "chunk_id": "chunk_en_agent_timeout_01",
        "content": "Per-tool timeout isolation enforces strict execution bounds: 10.0 seconds for SEARCH operations and 5.0 seconds for INSPECT operations, returning TIMEOUT status if exceeded.",
        "filename": "agent_timeouts.md",
    },
    "chunk_en_agent_loop_01": {
        "chunk_id": "chunk_en_agent_loop_01",
        "content": "Agent loop caps enforce a maximum iteration limit (default max_iterations=5). If an agent attempts running beyond the cap, execution halts with status LOOP_LIMIT_EXCEEDED.",
        "filename": "agent_loops.md",
    },
    "chunk_en_agent_endpoint_01": {
        "chunk_id": "chunk_en_agent_endpoint_01",
        "content": "The authenticated agent endpoint is exposed at POST /api/v1/projects/{project_id}/agent/workflow, accepting goal description and returning a comprehensive WorkflowReport.",
        "filename": "agent_endpoint.md",
    },
    "chunk_en_agent_report_01": {
        "chunk_id": "chunk_en_agent_report_01",
        "content": "WorkflowReport captures full agent trajectory telemetry including final_proposal, phase_history, tool_call_log with execution status, iteration count, and total duration.",
        "filename": "agent_schemas.md",
    },
    "chunk_en_db_pool_01": {
        "chunk_id": "chunk_en_db_pool_01",
        "content": "Async database engine configuration specifies DB_POOL_SIZE=10 connections and DB_MAX_OVERFLOW=20 connections with a pool timeout of 30 seconds for PostgreSQL asyncpg.",
        "filename": "database_pool.md",
    },
    "chunk_en_extensions_01": {
        "chunk_id": "chunk_en_extensions_01",
        "content": "File upload validation permits only supported file extensions: .pdf, .md, .txt, and .py. Uploading files with unsupported extensions immediately returns HTTP 400 Bad Request.",
        "filename": "file_validation.md",
    },
    "chunk_en_llm_client_01": {
        "chunk_id": "chunk_en_llm_client_01",
        "content": "DevPilot connects to LLM inference providers via OpenAI-compatible async clients configured with LLM_BASE_URL (e.g. Groq or OpenAI) and LLM_MODEL set to openai/gpt-oss-20b.",
        "filename": "llm_client.md",
    },
    "chunk_en_tokenizer_01": {
        "chunk_id": "chunk_en_tokenizer_01",
        "content": "The BM25 multilingual tokenizer uses regex pattern r'[\\w\\u0980-\\u09ff\\u200c\\u200d]+' to extract Unicode word boundaries for Bengali script, combining diacritics, and Latin Banglish.",
        "filename": "tokenizer_spec.md",
    },
    "chunk_en_bm25_cache_01": {
        "chunk_id": "chunk_en_bm25_cache_01",
        "content": "BM25Okapi index caching memoizes indexed corpus tokens by project_id or corpus content hash, eliminating redundant indexing overhead during frequent lexical lookups.",
        "filename": "bm25_cache.md",
    },
    "chunk_en_metrics_01": {
        "chunk_id": "chunk_en_metrics_01",
        "content": "Information retrieval metrics compute Recall@5 (1.0 if any ground-truth chunk is in top 5) and Mean Reciprocal Rank (MRR) based on the reciprocal rank of the first relevant document.",
        "filename": "metrics_ir.md",
    },
    "chunk_en_docker_01": {
        "chunk_id": "chunk_en_docker_01",
        "content": "DevPilot deployment utilizes multi-stage Docker builds running Uvicorn as a non-privileged system user on port 8000 with health checks configured at /health.",
        "filename": "docker_deploy.md",
    },
    "chunk_en_ci_01": {
        "chunk_id": "chunk_en_ci_01",
        "content": "GitHub Actions CI pipeline automatically executes the test suite with pytest and enforces static analysis and syntax checks via ruff on every pull request and push to main.",
        "filename": "ci_pipeline.md",
    },
    "chunk_en_doc_schema_01": {
        "chunk_id": "chunk_en_doc_schema_01",
        "content": "DocumentChunk database schema stores document_id, chunk_index, start_offset, end_offset, text content, and vector embedding column serialized as JSON float arrays.",
        "filename": "document_schema.md",
    },
    "chunk_en_citations_01": {
        "chunk_id": "chunk_en_citations_01",
        "content": "Grounded answer synthesis instructs the LLM to format source attributions with bracketed indices such as [1] or [2] corresponding directly to the numbered context chunks provided.",
        "filename": "citations_spec.md",
    },
    "chunk_en_refusal_01": {
        "chunk_id": "chunk_en_refusal_01",
        "content": "When retrieved context does not contain sufficient factual evidence to answer a user question, the RAG pipeline generates a polite refusal: 'I do not have enough information to answer.'",
        "filename": "refusals.md",
    },
    "chunk_en_swagger_01": {
        "chunk_id": "chunk_en_swagger_01",
        "content": "Interactive OpenAPI documentation and Swagger UI are accessible at /docs, allowing engineers to test endpoints and view Pydantic request and response schemas interactively.",
        "filename": "swagger_ui.md",
    },

    # --- Pure Bangla Script (বাংলা) Company Policy & System Features ---
    "chunk_bn_about_01": {
        "chunk_id": "chunk_bn_about_01",
        "content": "DevPilot একটি আধুনিক এআই-চালিত পেয়ার প্রোগ্রামিং অ্যাসিস্ট্যান্ট, যা সফটওয়্যার ইঞ্জিনিয়ারদের ডকুমেন্টেশন সার্চ, কোড নেভিগেশন এবং আর্কিটেকচারাল রিফ্যাক্টরিংয়ে সহায়তা করে।",
        "filename": "bn_about.md",
    },
    "chunk_bn_privacy_01": {
        "chunk_id": "chunk_bn_privacy_01",
        "content": "কোম্পানি ডাটা সুরক্ষা নীতি: ক্লায়েন্টদের কোড ও আপলোডকৃত ডকুমেন্ট সম্পূর্ণ এনক্রিপ্ট অবস্থায় সংরক্ষণ করা হয় এবং গ্রাহকের অনুমতি ব্যতিরেকে কোনো বাহ্যিক পাবলিক মডেলে ট্রেইনিংয়ের জন্য ব্যবহৃত হয় না।",
        "filename": "bn_privacy.md",
    },
    "chunk_bn_hybrid_01": {
        "chunk_id": "chunk_bn_hybrid_01",
        "content": "হাইব্রিড সার্চ পদ্ধতি: DevPilot ভেক্টর ডেনস সার্চ এবং BM25 লেক্সিক্যাল সার্চকে Reciprocal Rank Fusion (RRF, k=60) অ্যালগরিদমের মাধ্যমে একত্রিত করে সেরা ফলাফল প্রদান করে।",
        "filename": "bn_hybrid.md",
    },
    "chunk_bn_tenant_01": {
        "chunk_id": "chunk_bn_tenant_01",
        "content": "মাল্টি-টেন্যান্ট সিকিউরিটি পলিসি: এক গ্রাহক অন্য কোনো গ্রাহকের প্রজেক্টে প্রবেশের চেষ্টা করলে সিস্টেম নিরাপত্তা ব্যবস্থার মাধ্যমে তা শনাক্ত করে HTTP 403 Forbidden প্রদান করে।",
        "filename": "bn_tenant.md",
    },
    "chunk_bn_auth_01": {
        "chunk_id": "chunk_bn_auth_01",
        "content": "এপিআই অথেনটিকেশন নির্দেশিকা: প্রতিটি এপিআই রিকোয়েস্টে X-API-Key হেডার পাঠানো বাধ্যতামূলক; হেডার অনুপস্থিত বা খালি থাকলে সিস্টেম HTTP 401 Unauthorized ত্রুটি রিটার্ন করে।",
        "filename": "bn_auth.md",
    },
    "chunk_bn_upload_01": {
        "chunk_id": "chunk_bn_upload_01",
        "content": "ফাইল আপলোডের সাইজ লিমিট: ফাইল প্রতি সর্বোচ্চ অনুমোদিত সাইজ ১০ মেগাবাইট (১০,৪৮৫,৭৬০ বাইটস)। নির্ধারিত আকারের অতিরিক্ত ফাইল আপলোড করলে সিস্টেম HTTP 413 এরর প্রদর্শন করে।",
        "filename": "bn_upload.md",
    },
    "chunk_bn_formats_01": {
        "chunk_id": "chunk_bn_formats_01",
        "content": "অনুমোদিত ফাইল ফরম্যাট: DevPilot সিস্টেমে শুধুমাত্র .pdf, .md, .txt এবং .py এক্সটেনশনযুক্ত ফাইল আপলোড করা যাবে। অন্য কোনো ফরম্যাটের ফাইল গ্রহণ করা হয় না।",
        "filename": "bn_formats.md",
    },
    "chunk_bn_chunking_01": {
        "chunk_id": "chunk_bn_chunking_01",
        "content": "ডকুমেন্ট চাংকিং কনফিগারেশন: ডিফল্টভাবে টেক্সট ফাইলের চাঙ্ক সাইজ ৫১২ অক্ষর এবং সংলগ্ন চাঙ্কগুলোর মধ্যে ওভারল্যাপ ৬৪ অক্ষর নির্ধারণ করা থাকে।",
        "filename": "bn_chunking.md",
    },
    "chunk_bn_job_01": {
        "chunk_id": "chunk_bn_job_01",
        "content": "প্রসেসিং জবের জীবনচক্র: ব্যাকগ্রাউন্ডে টেক্সট এক্সট্রাকশন চলাকালে জবের স্ট্যাটাস PENDING থেকে শুরু হয়ে IN_PROGRESS এবং পরিশেষে COMPLETED অথবা FAILED অবস্থায় পৌঁছে।",
        "filename": "bn_job.md",
    },
    "chunk_bn_background_01": {
        "chunk_id": "chunk_bn_background_01",
        "content": "অ্যাসিনক্রোনাস ব্যাকগ্রাউন্ড প্রসেসিং: ডকুমেন্ট আপলোড হওয়ার পর FastAPI ব্যাকগ্রাউন্ড টাস্ক পৃথক ডাটাবেস সেশনে চাঙ্ক তৈরি এবং ভেক্টরাইজেশন সম্পন্ন করে।",
        "filename": "bn_background.md",
    },
    "chunk_bn_agent_01": {
        "chunk_id": "chunk_bn_agent_01",
        "content": "বাউন্ডেড এজেন্ট ওয়ার্কফ্লো: DevPilot এজেন্ট কঠোরভাবে ৪টি ধাপে কাজ করে: SEARCH (অনুসন্ধান) -> INSPECT (পরিদর্শন) -> SUMMARIZE (সারসংক্ষেপ) -> PROPOSE (প্রস্তাব)।",
        "filename": "bn_agent.md",
    },
    "chunk_bn_llm_01": {
        "chunk_id": "chunk_bn_llm_01",
        "content": "লার্জ ল্যাঙ্গুয়েজ মডেল পলিসি: DevPilot সিস্টেমে গ্রক অথবা ওপেনএআই সামঞ্জস্যপূর্ণ এন্ডপয়েন্টের মাধ্যমে gpt-oss-20b মডেল গ্রাউন্ডেড উত্তর জেনারেশনের জন্য ব্যবহৃত হয়।",
        "filename": "bn_llm.md",
    },
    "chunk_bn_embedding_01": {
        "chunk_id": "chunk_bn_embedding_01",
        "content": "বহুভাষিক এমবেডিং মডেল: DevPilot বহুভাষিক মিনিএলএম মডেল (paraphrase-multilingual-MiniLM-L12-v2) ব্যবহার করে ৩৮৪-ডাইমেনশনের ঘন ভেক্টর তৈরি করে।",
        "filename": "bn_embedding.md",
    },
    "chunk_bn_hallucination_01": {
        "chunk_id": "chunk_bn_hallucination_01",
        "content": "হ্যালুসিনেশন ও বিভ্রান্তি প্রতিরোধ: আনসাপোর্টেড ক্লেইম রেট মেট্রিক্সে কোনো বাক্যের সাথে রেফারেন্স চাঙ্কের টোকেন মিল ৪০% এর কম হলে তা ভিত্তিহীন তথ্য হিসেবে চিহ্নিত করা হয়।",
        "filename": "bn_hallucination.md",
    },
    "chunk_bn_rerank_01": {
        "chunk_id": "chunk_bn_rerank_01",
        "content": "ক্রস-এনকোডার রি-র‍্যাংকিং: প্রাথমিক রিট্রিভাল থেকে প্রাপ্ত প্রার্থীদের পুনরায় মূল্যায়ন করতে cross-encoder/ms-marco-MiniLM-L-6-v2 মডেল ব্যবহার করে সঠিক স্কোর নির্ধারণ করা হয়।",
        "filename": "bn_rerank.md",
    },
    "chunk_bn_rerank_fallback_01": {
        "chunk_id": "chunk_bn_rerank_fallback_01",
        "content": "রি-র‍্যাঙ্কার ফ্যালব্যাক পলিসি: ট্রান্সফরমার মডেল লোড ব্যর্থ হলে সিস্টেম RERANKER_FALLBACK_ACTIVE ওয়ার্নিং লগ করে এবং লেক্সিক্যাল হিউরিস্টিক পদ্ধতিতে র‍্যাংকিং করে।",
        "filename": "bn_fallback.md",
    },
    "chunk_bn_alembic_01": {
        "chunk_id": "chunk_bn_alembic_01",
        "content": "ডাটাবেস স্কিমা মাইগ্রেশন: পোস্টগ্রেস ডাটাবেস টেবিল আপডেট ও মাইগ্রেশনের জন্য অ্যালেমবিক টুল ব্যবহার করে 'alembic upgrade head' কমান্ড এক্সিকিউট করা হয়।",
        "filename": "bn_alembic.md",
    },
    "chunk_bn_db_pool_01": {
        "chunk_id": "chunk_bn_db_pool_01",
        "content": "ডাটাবেস কানেকশন পুলিং: সিস্টেম পারফরম্যান্স বজায় রাখতে ডাটাবেস পুলে স্বাভাবিক সাইজ ১০ এবং সর্বোচ্চ অতিরিক্ত সংযোগ ২০ টি নির্ধারিত থাকে।",
        "filename": "bn_db_pool.md",
    },
    "chunk_bn_timeout_01": {
        "chunk_id": "chunk_bn_timeout_01",
        "content": "টুল টাইমআউট সীমা: এজেন্টের SEARCH টাস্কের জন্য সর্বোচ্চ ১০.০ সেকেন্ড এবং INSPECT টাস্কের জন্য সর্বোচ্চ ৫.০ সেকেন্ড সময় বরাদ্দ থাকে।",
        "filename": "bn_timeout.md",
    },
    "chunk_bn_loop_cap_01": {
        "chunk_id": "chunk_bn_loop_cap_01",
        "content": "এজেন্ট লুপ ক্যাপ লিমিট: অসীম পুনরাবৃত্তি বা রানঅ্যাওয়ে বন্ধ করতে এজেন্ট সর্বোচ্চ ৫টি ইটারেশন পর্যন্ত কাজ করতে পারে; এর বেশি হলে সিস্টেম স্বয়ংক্রিয়ভাবে থেমে যায়।",
        "filename": "bn_loop.md",
    },
    "chunk_bn_sha256_01": {
        "chunk_id": "chunk_bn_sha256_01",
        "content": "কন্টেন্ট হ্যাশিং ও ডুপ্লিকেট রোধ: আপলোডকৃত ফাইলের সত্যতা এবং ডুপ্লিকেট শনাক্ত করতে লোকাল স্টোরেজ সার্ভিস SHA-256 হেক্সাডেসিমেল ডাইজেস্ট হিসাব করে।",
        "filename": "bn_sha256.md",
    },
    "chunk_bn_leave_01": {
        "chunk_id": "chunk_bn_leave_01",
        "content": "কর্মচারী ছুটি নীতি: পূর্ণকালীন সফটওয়্যার ইঞ্জিনিয়ারগণ বছরে ২০ দিন বার্ষিক ছুটি (Annual Leave) এবং ১০ দিন অসুস্থতাজনিত পেইড মেডিকেল লিভ পেয়ে থাকেন।",
        "filename": "bn_leave.md",
    },
    "chunk_bn_remote_01": {
        "chunk_id": "chunk_bn_remote_01",
        "content": "রিমোট ওয়ার্ক এবং হাইব্রিড পলিসি: প্রকৌশলীরা সপ্তাহে ৩ দিন হোম অফিস এবং ২ দিন অফিসে কাজ করার হাইব্রিড মডেল অনুসরণ করেন, তবে প্রয়োজনীয় সরঞ্জামের খরচ কোম্পানি বহন করে।",
        "filename": "bn_remote.md",
    },
    "chunk_bn_code_review_01": {
        "chunk_id": "chunk_bn_code_review_01",
        "content": "কোড রিভিউ এবং পিআর নিয়মাবলী: মূল প্রোডাকশন শাখায় কোড মার্জ করার আগে ন্যূনতম অন্তত দুইজন সিনিয়র ডেভেলপারের অ্যাপ্রুভাল এবং ১০০% টেস্ট পাস নিশ্চিত করতে হয়।",
        "filename": "bn_code_review.md",
    },
    "chunk_bn_sla_01": {
        "chunk_id": "chunk_bn_sla_01",
        "content": "ইনসিডেন্ট রেসপন্স ও এসএলএ: প্রোডাকশন সিস্টেমে কোনো গুরুতর সমস্যা (P0 ইনসিডেন্ট) দেখা দিলে অন-কল ইঞ্জিনিয়ারিং টিমকে ১৫ মিনিটের মধ্যে প্রতিক্রিয়া জানাতে হয়।",
        "filename": "bn_sla.md",
    },
    "chunk_bn_security_rotation_01": {
        "chunk_id": "chunk_bn_security_rotation_01",
        "content": "নিরাপত্তা ও পাসওয়ার্ড রোটেশন পলিসি: নিরাপত্তা ঝুঁকি এড়াতে সমস্ত ডেভেলপার এবং অ্যাডমিন অ্যাকাউন্টের এপিআই কি ও পাসওয়ার্ড প্রতি ৯০ দিন অন্তর পরিবর্তন করা বাধ্যতামূলক।",
        "filename": "bn_rotation.md",
    },
    "chunk_bn_docs_01": {
        "chunk_id": "chunk_bn_docs_01",
        "content": "টেকনিক্যাল ডকুমেন্টেশন গাইডলাইন: প্রতিটি নতুন এপিআই এন্ডপয়েন্ট এবং মডিউলে পূর্ণাঙ্গ পাইথন ডকস্ট্রিং, প্যারামিটার বিবরণ এবং টাইপ অ্যানোটেশন থাকা বাধ্যতামূলক।",
        "filename": "bn_docs.md",
    },
    "chunk_bn_onboarding_01": {
        "chunk_id": "chunk_bn_onboarding_01",
        "content": "নতুন ডেভেলপার অনবোর্ডিং প্রক্রিয়া: নতুন যোগদানকারী ইঞ্জিনিয়ারদের প্রথম সপ্তাহে একজন মেন্টর নিয়োগ করা হয় এবং লোকাল ডেভেলপমেন্ট এনভায়রনমেন্ট সেটআপে সহায়তা প্রদান করা হয়।",
        "filename": "bn_onboarding.md",
    },
    "chunk_bn_ci_01": {
        "chunk_id": "chunk_bn_ci_01",
        "content": "সিআই পাইপলাইন ও টেস্ট কভারেজ: গিটহাব অ্যাকশন্সে স্বয়ংক্রিয় টেস্ট চালানোর সময় কোড কভারেজ কমপক্ষে ৮০% বজায় রাখা নতুন কোড মার্জের পূর্বশর্ত।",
        "filename": "bn_ci.md",
    },
    "chunk_bn_license_01": {
        "chunk_id": "chunk_bn_license_01",
        "content": "ওপেন সোর্স লাইসেন্স কমপ্লায়েন্স: কোনো নতুন থার্ড-পার্টি লাইব্রেরি যুক্ত করার পূর্বে তা Apache 2.0 অথবা MIT লাইসেন্সভুক্ত কি না তা আইন বিভাগ কর্তৃক যাচাই হতে হয়।",
        "filename": "bn_license.md",
    },
    "chunk_bn_backup_01": {
        "chunk_id": "chunk_bn_backup_01",
        "content": "ডাটাবেস ব্যাকআপ ও দুর্যোগ পুনরুদ্ধার: ক্লাউড ডাটাবেসের সম্পূর্ণ স্ন্যাপশট প্রতিদিন মধ্যরাতে স্বয়ংক্রিয়ভাবে ব্যাকআপ নেওয়া হয় এবং তা ৩০ দিন পর্যন্ত সংরক্ষিত থাকে।",
        "filename": "bn_backup.md",
    },
    "chunk_bn_comms_01": {
        "chunk_id": "chunk_bn_comms_01",
        "content": "অভ্যন্তরীণ যোগাযোগ ও মেসেজিং নিয়ম: ইঞ্জিনিয়ারিং টিম প্রতিদিনের দ্রুত আপডেটের জন্য স্ল্যাক চ্যানেল ব্যবহার করে এবং দীর্ঘমেয়াদী সিদ্ধান্তের জন্য লিখিত RFC নথি তৈরি করে।",
        "filename": "bn_comms.md",
    },
    "chunk_bn_appraisal_01": {
        "chunk_id": "chunk_bn_appraisal_01",
        "content": "বার্ষিক মূল্যায়ন ও পদোন্নতি পদ্ধতি: প্রতি বছরের ডিসেম্বর মাসে প্রকৌশলীদের কোড কোয়ালিটি, সিস্টেম আর্কিটেকচার অবদান এবং টিম সহযোগিতার ওপর ভিত্তি করে পারফরম্যান্স রিভিউ অনুষ্ঠিত হয়।",
        "filename": "bn_appraisal.md",
    },

    # --- Romanized Banglish Corpus Chunks ---
    "chunk_bng_hybrid_01": {
        "chunk_id": "chunk_bng_hybrid_01",
        "content": "DevPilot a hybrid search e dense vector similarity ar BM25 keyword matching ke Reciprocal Rank Fusion (RRF, k=60) diye combine kora hoy jate best chunks rank e ashe.",
        "filename": "bng_hybrid.md",
    },
    "chunk_bng_upload_01": {
        "chunk_id": "chunk_bng_upload_01",
        "content": "DevPilot a file upload er max limit holo 10MB. 10MB er beshi boro file dile system HTTP 413 Payload Too Large error return kore reject kore dei.",
        "filename": "bng_upload.md",
    },
    "chunk_bng_auth_01": {
        "chunk_id": "chunk_bng_auth_01",
        "content": "API call korar shomoy request e X-API-Key header pathate hoy. Jodi API key missing ba empty thake tahole HTTP 401 Unauthorized error ashbe.",
        "filename": "bng_auth.md",
    },
    "chunk_bng_tenant_01": {
        "chunk_id": "chunk_bng_tenant_01",
        "content": "Ak project er tenant onno project access korte chaile verify_project_tenant_access check fail kore ar HTTP 403 Forbidden error response pathay.",
        "filename": "bng_tenant.md",
    },
    "chunk_bng_config_01": {
        "chunk_id": "chunk_bng_config_01",
        "content": "Config file src/core/config.py te CHUNK_SIZE er default value holo 512 characters ar CHUNK_OVERLAP holo 64 characters.",
        "filename": "bng_config.md",
    },
    "chunk_bng_embedding_01": {
        "chunk_id": "chunk_bng_embedding_01",
        "content": "DevPilot vector embeddings er jonno sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 model use kore ja 384 dimensional dense vector banay.",
        "filename": "bng_embedding.md",
    },
    "chunk_bng_rerank_01": {
        "chunk_id": "chunk_bng_rerank_01",
        "content": "Top candidate chunk gulo re-evaluate korte cross-encoder/ms-marco-MiniLM-L-6-v2 model use kora hoy ja full query-document interaction score kore.",
        "filename": "bng_rerank.md",
    },
    "chunk_bng_fallback_01": {
        "chunk_id": "chunk_bng_fallback_01",
        "content": "Transformer cross-encoder load na hole RerankerService warning log kore 'RERANKER_FALLBACK_ACTIVE' ar term overlap heuristic diye ranking kore.",
        "filename": "bng_fallback.md",
    },
    "chunk_bng_hallucination_01": {
        "chunk_id": "chunk_bng_hallucination_01",
        "content": "Hallucination detect korar jonno unsupported_claims_rate metric use kora hoy. Sentence er token overlap context chunk er shathe 40% er kom hole unsupported dhora hoy.",
        "filename": "bng_hallucination.md",
    },
    "chunk_bng_jobs_01": {
        "chunk_id": "chunk_bng_jobs_01",
        "content": "ProcessingJob er status gulo holo PENDING, IN_PROGRESS, COMPLETED, ar FAILED. Clients job_id diye progress poll korte pare.",
        "filename": "bng_jobs.md",
    },
    "chunk_bng_alembic_01": {
        "chunk_id": "chunk_bng_alembic_01",
        "content": "Database schema migration apply korte 'alembic upgrade head' command run korte hoy ja PostgreSQL table gulo update kore dey.",
        "filename": "bng_alembic.md",
    },
    "chunk_bng_sha256_01": {
        "chunk_id": "chunk_bng_sha256_01",
        "content": "Duplicate file detect korar jonno LocalStorageService file er raw bytes theke hexadecimal SHA-256 hash generate kore check kore.",
        "filename": "bng_sha256.md",
    },
    "chunk_bng_background_01": {
        "chunk_id": "chunk_bng_background_01",
        "content": "Upload endpoint block na kore asynchronous processing er jonno FastAPI BackgroundTasks use kora hoy ja separate database session e chunk create kore.",
        "filename": "bng_background.md",
    },
    "chunk_bng_pdf_01": {
        "chunk_id": "chunk_bng_pdf_01",
        "content": "PDF file theke text extract korte pypdf package er PdfReader class use hoy ja page by page text porhe boundary marker add kore.",
        "filename": "bng_pdf.md",
    },
    "chunk_bng_agent_fsm_01": {
        "chunk_id": "chunk_bng_agent_fsm_01",
        "content": "DevPilot bounded agent 4 ta fixed phase e kaj kore: SEARCH -> INSPECT -> SUMMARIZE -> PROPOSE. Kono phase skip ba ultopalta progression allowed na.",
        "filename": "bng_agent_fsm.md",
    },
    "chunk_bng_firewall_01": {
        "chunk_id": "chunk_bng_firewall_01",
        "content": "GuardedToolDispatcher e Pydantic validation firewall ache. Vul input dile ToolExecutionStatus.VALIDATION_ERROR return kore self-correction er সুযোগ dey.",
        "filename": "bng_firewall.md",
    },
    "chunk_bng_timeout_01": {
        "chunk_id": "chunk_bng_timeout_01",
        "content": "Agent tool execution timeout isolated: SEARCH operation er jonno 10.0 seconds ar INSPECT operation er jonno 5.0 seconds limit fixed.",
        "filename": "bng_timeout.md",
    },
    "chunk_bng_loop_cap_01": {
        "chunk_id": "chunk_bng_loop_cap_01",
        "content": "Agent jate infinite loop e na pore tai max_iterations=5 loop cap deya ache. Limit cross korle LOOP_LIMIT_EXCEEDED status return kore stop hoy.",
        "filename": "bng_loop_cap.md",
    },
    "chunk_bng_endpoint_01": {
        "chunk_id": "chunk_bng_endpoint_01",
        "content": "Agent workflow run korar route path holo POST /api/v1/projects/{project_id}/agent/workflow ja goal niye full WorkflowReport return kore.",
        "filename": "bng_endpoint.md",
    },
    "chunk_bng_report_01": {
        "chunk_id": "chunk_bng_report_01",
        "content": "WorkflowReport response model e final_proposal, phase_history, tool_call_log, iteration count ar execution execution_time_seconds thake.",
        "filename": "bng_report.md",
    },
    "chunk_bng_db_pool_01": {
        "chunk_id": "chunk_bng_db_pool_01",
        "content": "PostgreSQL database connection pool e normal size 10 connections ar max overflow 20 connections set kora ache.",
        "filename": "bng_db_pool.md",
    },
    "chunk_bng_extensions_01": {
        "chunk_id": "chunk_bng_extensions_01",
        "content": "Allowed file extensions holo .pdf, .md, .txt, ar .py. Onno extension er file upload korle HTTP 400 Bad Request error ashbe.",
        "filename": "bng_extensions.md",
    },
    "chunk_bng_llm_client_01": {
        "chunk_id": "chunk_bng_llm_client_01",
        "content": "LLM calling er jonno OpenAI compatible async client use hoy jar model default openai/gpt-oss-20b ar base url Groq ba OpenAI.",
        "filename": "bng_llm_client.md",
    },
    "chunk_bng_tokenizer_01": {
        "chunk_id": "chunk_bng_tokenizer_01",
        "content": "Bangla ar Banglish text tokenize korte regex pattern [\\w\\u0980-\\u09ff\\u200c\\u200d]+ use hoy ja Bengali script ar combining signs handle kore.",
        "filename": "bng_tokenizer.md",
    },
    "chunk_bng_bm25_cache_01": {
        "chunk_id": "chunk_bng_bm25_cache_01",
        "content": "BM25 index cache memory te rakha hoy project_id diye cache key baniye, jate proti query te notun kore index build korte na hoy.",
        "filename": "bng_bm25_cache.md",
    },
    "chunk_bng_leave_01": {
        "chunk_id": "chunk_bng_leave_01",
        "content": "Company leave policy te engineers der jonno bochore 20 din annual vacation leave ar 10 din paid sick medical leave pawa jay.",
        "filename": "bng_leave.md",
    },
    "chunk_bng_remote_01": {
        "chunk_id": "chunk_bng_remote_01",
        "content": "Remote work rule holo hybrid model: shoptah e 3 din work from home (WFH) ar 2 din office kora lage.",
        "filename": "bng_remote.md",
    },
    "chunk_bng_pr_01": {
        "chunk_id": "chunk_bng_pr_01",
        "content": "Production e code merge korar age pull request e minimum 2 jon senior dev er approval ar 100% test pass kora mandatory.",
        "filename": "bng_pr.md",
    },
    "chunk_bng_incident_01": {
        "chunk_id": "chunk_bng_incident_01",
        "content": "P0 production incident er jonno on-call engineering team er response SLA holo maximum 15 minutes er moddhe acknowledge kora.",
        "filename": "bng_incident.md",
    },
    "chunk_bng_rotation_01": {
        "chunk_id": "chunk_bng_rotation_01",
        "content": "Security karone shob developer der account password ar API key proti 90 days por por rotate ba change korte hoy.",
        "filename": "bng_rotation.md",
    },
    "chunk_bng_ci_01": {
        "chunk_id": "chunk_bng_ci_01",
        "content": "GitHub Actions CI pipeline e automated tests run hoy ar minimum test code coverage 80% maintain korte hoy.",
        "filename": "bng_ci.md",
    },
    "chunk_bng_backup_01": {
        "chunk_id": "chunk_bng_backup_01",
        "content": "Production database protidin midnight e automatic backup hoy ar snapshots gulo 30 days porjonto cloud storage e store thake.",
        "filename": "bng_backup.md",
    },
    "chunk_bng_docker_01": {
        "chunk_id": "chunk_bng_docker_01",
        "content": "DevPilot docker container run korte 'docker compose up --build' command use kora hoy port 8000 e service serve korte.",
        "filename": "bng_docker.md",
    },
}

# General cross-domain distractors to test retrieval discrimination
DISTRACTORS = [
    {
        "chunk_id": "distractor_weather_01",
        "content": "Meteorological report: Tropical monsoon atmospheric conditions bring precipitation and high relative humidity across coastal regions.",
        "filename": "weather.md",
    },
    {
        "chunk_id": "distractor_recipe_01",
        "content": "Traditional culinary recipe: Marinate chicken with yogurt, turmeric, cumin, and garam masala for authentic biryani preparation.",
        "filename": "recipe.md",
    },
    {
        "chunk_id": "distractor_astronomy_01",
        "content": "Astrophysics summary: James Webb Space Telescope observes high-redshift early galaxies forming within 400 million years after the Big Bang.",
        "filename": "astronomy.md",
    },
    {
        "chunk_id": "distractor_sports_01",
        "content": "Cricket match analysis: The opening batsmen established a steady 120-run partnership with disciplined stroke play through the off-side.",
        "filename": "sports.md",
    },
    {
        "chunk_id": "distractor_bn_history_01",
        "content": "ইতিহাস পর্যালোচনা: ষোড়শ শতকে বাংলার সুবেদারগণ সুসংগঠিত রাজস্ব ব্যবস্থা ও বাণিজ্য নেটওয়ার্ক বিস্তার করেছিলেন।",
        "filename": "bn_history.md",
    },
]


# -----------------------------------------------------------------------------
# 2. DEFINITION OF THE 100 QUERIES
# -----------------------------------------------------------------------------
# Format: (query_id, language, query, [ground_truth_chunk_ids], reference_answer)
QUERIES_DATA = [
    # =========================================================================
    # SLICE 1: ENGLISH (34 Queries: q_001 to q_034)
    # =========================================================================
    (
        "q_001", "english",
        "What are the default values of CHUNK_SIZE and CHUNK_OVERLAP in DevPilot configuration?",
        ["chunk_en_config_01"],
        "CHUNK_SIZE defaults to 512 and CHUNK_OVERLAP defaults to 64 in src/core/config.py.",
    ),
    (
        "q_002", "english",
        "What HTTP status code is raised when the X-API-Key header is missing or empty?",
        ["chunk_en_security_01"],
        "The security layer raises HTTP 401 Unauthorized when X-API-Key is missing or empty.",
    ),
    (
        "q_003", "english",
        "What error is returned when an authenticated user attempts to access another tenant's project?",
        ["chunk_en_tenant_01"],
        "Cross-tenant access triggers verify_project_tenant_access and returns HTTP 403 Forbidden.",
    ),
    (
        "q_004", "english",
        "What smoothing constant k is used in Reciprocal Rank Fusion (RRF) algorithm?",
        ["chunk_en_rrf_01"],
        "DevPilot uses constant k=60 in the Reciprocal Rank Fusion formula.",
    ),
    (
        "q_005", "english",
        "Which Python library and class provide sparse lexical search in DevPilot?",
        ["chunk_en_bm25_01"],
        "DevPilot uses BM25Okapi from the rank-bm25 package for sparse search.",
    ),
    (
        "q_006", "english",
        "What dense vector model and dimensions are configured for multilingual text embeddings?",
        ["chunk_en_embedding_01"],
        "DevPilot uses sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 producing 384-dimensional dense vectors.",
    ),
    (
        "q_007", "english",
        "Which cross-encoder model checkpoint is deployed for candidate reranking?",
        ["chunk_en_reranker_01"],
        "Candidate reranking deploys cross-encoder/ms-marco-MiniLM-L-6-v2.",
    ),
    (
        "q_008", "english",
        "What log warning is emitted when cross-encoder transformer fails and falls back to heuristics?",
        ["chunk_en_rerank_fallback_01"],
        "When reranker falls back, it logs warning 'RERANKER_FALLBACK_ACTIVE'.",
    ),
    (
        "q_009", "english",
        "What token overlap threshold ratio classifies a generated claim as supported vs unsupported?",
        ["chunk_en_unsupported_01"],
        "The unsupported claims rate metric enforces a threshold of 0.40 sentence-to-chunk token overlap ratio.",
    ),
    (
        "q_010", "english",
        "What is the maximum allowed file upload size and what HTTP error is returned if exceeded?",
        ["chunk_en_storage_01"],
        "LocalStorageService restricts uploads to 10MB (10,485,760 bytes), returning HTTP 413 for oversized files.",
    ),
    (
        "q_011", "english",
        "What are the valid lifecycle status values of a ProcessingJob in DevPilot?",
        ["chunk_en_job_status_01"],
        "ProcessingJob statuses are PENDING, IN_PROGRESS, COMPLETED, and FAILED.",
    ),
    (
        "q_012", "english",
        "Which Alembic command applies database migrations to upgrade the schema to latest version?",
        ["chunk_en_alembic_01"],
        "Schema migrations are upgraded using the command 'alembic upgrade head'.",
    ),
    (
        "q_013", "english",
        "What hashing algorithm does LocalStorageService compute for file deduplication?",
        ["chunk_en_storage_hash_01"],
        "LocalStorageService computes a hexadecimal SHA-256 digest over file content.",
    ),
    (
        "q_014", "english",
        "How does the document ingestion endpoint handle extraction without blocking the HTTP request?",
        ["chunk_en_background_01"],
        "Text extraction runs asynchronously via FastAPI BackgroundTasks with an independent DB session.",
    ),
    (
        "q_015", "english",
        "Which library extracts PDF pages and what boundary delimiter separates pages in text?",
        ["chunk_en_pdf_01"],
        "PDF extraction uses pypdf.PdfReader and separates pages with '--- Page N ---' boundary markers.",
    ),
    (
        "q_016", "english",
        "How are application configuration settings defined and loaded in DevPilot?",
        ["chunk_en_pydantic_01"],
        "Settings are managed via Pydantic Settings with automatic loading from .env files.",
    ),
    (
        "q_017", "english",
        "What is the exact 4-phase sequence enforced by the bounded agent state machine?",
        ["chunk_en_agent_fsm_01"],
        "The bounded agent enforces the sequence: SEARCH -> INSPECT -> SUMMARIZE -> PROPOSE.",
    ),
    (
        "q_018", "english",
        "How does GuardedToolDispatcher handle malformed tool invocation arguments?",
        ["chunk_en_agent_firewall_01"],
        "GuardedToolDispatcher catches malformed inputs and returns ToolExecutionStatus.VALIDATION_ERROR.",
    ),
    (
        "q_019", "english",
        "What are the execution timeout limits for SEARCH and INSPECT agent tools?",
        ["chunk_en_agent_timeout_01"],
        "Per-tool timeout isolation enforces 10.0 seconds for SEARCH and 5.0 seconds for INSPECT.",
    ),
    (
        "q_020", "english",
        "What loop cap is enforced on the agent workflow and what status occurs upon breach?",
        ["chunk_en_agent_loop_01"],
        "Agent loop cap enforces max_iterations=5, halting with LOOP_LIMIT_EXCEEDED if exceeded.",
    ),
    (
        "q_021", "english",
        "What is the exact route path of the authenticated agent workflow endpoint?",
        ["chunk_en_agent_endpoint_01"],
        "The agent workflow is exposed at POST /api/v1/projects/{project_id}/agent/workflow.",
    ),
    (
        "q_022", "english",
        "What telemetry information is included in the WorkflowReport response model?",
        ["chunk_en_agent_report_01"],
        "WorkflowReport includes final_proposal, phase_history, tool_call_log, iteration count, and duration.",
    ),
    (
        "q_023", "english",
        "What are the configured database connection pool size and max overflow parameters?",
        ["chunk_en_db_pool_01"],
        "PostgreSQL async engine configures DB_POOL_SIZE=10 and DB_MAX_OVERFLOW=20.",
    ),
    (
        "q_024", "english",
        "Which file extensions are accepted by DevPilot document upload validation?",
        ["chunk_en_extensions_01"],
        "Allowed file extensions are .pdf, .md, .txt, and .py.",
    ),
    (
        "q_025", "english",
        "What default LLM model name and client compatibility are configured for answer synthesis?",
        ["chunk_en_llm_client_01"],
        "DevPilot uses OpenAI-compatible async clients with LLM_MODEL set to openai/gpt-oss-20b.",
    ),
    (
        "q_026", "english",
        "What regex pattern is used by the multilingual BM25 tokenizer for Unicode script matching?",
        ["chunk_en_tokenizer_01"],
        "The tokenizer uses r'[\\w\\u0980-\\u09ff\\u200c\\u200d]+' to handle Bengali and Latin tokens.",
    ),
    (
        "q_027", "english",
        "How does DevPilot prevent rebuilding BM25 indices on repetitive lexical queries?",
        ["chunk_en_bm25_cache_01"],
        "BM25Okapi instances are memoized in an in-memory cache keyed by project_id or corpus hash.",
    ),
    (
        "q_028", "english",
        "How is Recall@5 defined in DevPilot information retrieval evaluation?",
        ["chunk_en_metrics_01"],
        "Recall@5 is 1.0 if at least one ground-truth chunk appears in top-5 retrieved results, else 0.0.",
    ),
    (
        "q_029", "english",
        "What user privileges and port are configured for production Docker container deployments?",
        ["chunk_en_docker_01"],
        "Docker container runs as a non-privileged user serving Uvicorn on port 8000.",
    ),
    (
        "q_030", "english",
        "Which automated checks and tools run in GitHub Actions continuous integration?",
        ["chunk_en_ci_01"],
        "GitHub Actions CI runs pytest for unit/integration tests and ruff for linting and syntax checks.",
    ),
    (
        "q_031", "english",
        "What metadata and offset fields are stored in the DocumentChunk table schema?",
        ["chunk_en_doc_schema_01"],
        "DocumentChunk stores document_id, chunk_index, start_offset, end_offset, content, and embedding.",
    ),
    (
        "q_032", "english",
        "What citation syntax must the LLM use to cite factual chunks in grounded answers?",
        ["chunk_en_citations_01"],
        "Grounded answers use bracketed citation indices like [1] or [2] corresponding to context chunks.",
    ),
    (
        "q_033", "english",
        "What standard refusal message is returned when retrieved chunks lack relevant evidence?",
        ["chunk_en_refusal_01"],
        "When context is insufficient, DevPilot returns: 'I do not have enough information to answer.'",
    ),
    (
        "q_034", "english",
        "Where can developers view interactive OpenAPI documentation and test API endpoints?",
        ["chunk_en_swagger_01"],
        "Interactive Swagger UI documentation is available at the /docs URL path.",
    ),

    # =========================================================================
    # SLICE 2: PURE BANGLA SCRIPT (33 Queries: q_035 to q_067)
    # =========================================================================
    (
        "q_035", "bangla",
        "DevPilot কী ধরনের সিস্টেম এবং এটি সফটওয়্যার ডেভেলপারদের কীভাবে সহায়তা করে?",
        ["chunk_bn_about_01"],
        "DevPilot একটি এআই পেয়ার প্রোগ্রামিং অ্যাসিস্ট্যান্ট যা ডকুমেন্টেশন সার্চ, কোড নেভিগেশন ও রিফ্যাক্টরিংয়ে সহায়তা করে।",
    ),
    (
        "q_036", "bangla",
        "গ্রাহকদের কোড এবং আপলোডকৃত ডেটার নিরাপত্তা সম্পর্কিত কোম্পানির পলিসি কী?",
        ["chunk_bn_privacy_01"],
        "কোড ও ডেটা এনক্রিপ্ট অবস্থায় সংরক্ষিত থাকে এবং অনুমতি ছাড়া পাবলিক মডেল ট্রেইনিংয়ে ব্যবহৃত হয় না।",
    ),
    (
        "q_037", "bangla",
        "DevPilot এ হাইব্রিড সার্চ পদ্ধতি কীভাবে কাজ করে?",
        ["chunk_bn_hybrid_01"],
        "হাইব্রিড সার্চ ভেক্টর ডেনস সার্চ ও BM25 লেক্সিক্যাল সার্চকে Reciprocal Rank Fusion (k=60) দিয়ে একত্রিত করে।",
    ),
    (
        "q_038", "bangla",
        "অন্য কোনো টেন্যান্টের প্রজেক্টে প্রবেশের চেষ্টা করলে সিস্টেম কী এরর প্রদর্শন করে?",
        ["chunk_bn_tenant_01"],
        "অননুমোদিত ক্রস-টেন্যান্ট প্রবেশের চেষ্টায় সিস্টেম HTTP 403 Forbidden এরর রিটার্ন করে।",
    ),
    (
        "q_039", "bangla",
        "DevPilot এপিআই কলের জন্য কোন হেডারটি বাধ্যতামূলক এবং না থাকলে কী এরর হয়?",
        ["chunk_bn_auth_01"],
        "প্রতিটি রিকোয়েস্টে X-API-Key হেডার আবশ্যক; অনুপস্থিত থাকলে HTTP 401 Unauthorized ত্রুটি ঘটে।",
    ),
    (
        "q_040", "bangla",
        "ডকুমেন্ট আপলোডের জন্য সর্বোচ্চ ফাইল সাইজের সীমা কত এবং অতিক্রম করলে কী ঘটে?",
        ["chunk_bn_upload_01"],
        "সর্বোচ্চ সাইজ ১০ মেগাবাইট; নির্ধারিত সাইজের অতিরিক্ত ফাইল আপলোড করলে HTTP 413 এরর প্রদর্শন করে।",
    ),
    (
        "q_041", "bangla",
        "সিস্টেমে কোন কোন ফাইল ফরম্যাট আপলোড করার অনুমতি রয়েছে?",
        ["chunk_bn_formats_01"],
        "সিস্টেমে শুধুমাত্র .pdf, .md, .txt এবং .py এক্সটেনশনযুক্ত ফাইল আপলোড করা যায়।",
    ),
    (
        "q_042", "bangla",
        "টেক্সট চাংকিংয়ের ক্ষেত্রে ডিফল্ট চাঙ্ক সাইজ এবং ওভারল্যাপের মান কত?",
        ["chunk_bn_chunking_01"],
        "ডিফল্ট চাঙ্ক সাইজ ৫১২ অক্ষর এবং সংলগ্ন চাঙ্কের মধ্যে ওভারল্যাপ ৬৪ অক্ষর।",
    ),
    (
        "q_043", "bangla",
        "প্রসেসিং জবের সম্ভাব্য স্ট্যাটাস বা পর্যায়গুলো কী কী হতে পারে?",
        ["chunk_bn_job_01"],
        "প্রসেসিং জবের স্ট্যাটাসগুলো হলো PENDING, IN_PROGRESS, COMPLETED এবং FAILED।",
    ),
    (
        "q_044", "bangla",
        "ডকুমেন্ট প্রসেসিং ব্যাকগ্রাউন্ডে কীভাবে সম্পন্ন হয়?",
        ["chunk_bn_background_01"],
        "FastAPI ব্যাকগ্রাউন্ড টাস্কের মাধ্যমে পৃথক ডাটাবেস সেশনে চাঙ্ক তৈরি ও ভেক্টরাইজেশন সম্পন্ন হয়।",
    ),
    (
        "q_045", "bangla",
        "বাউন্ডেড এজেন্টের কাজের ধারাবাহিক ৪টি ধাপ কী কী?",
        ["chunk_bn_agent_01"],
        "এজেন্ট ৪টি ধাপে কাজ করে: SEARCH -> INSPECT -> SUMMARIZE -> PROPOSE।",
    ),
    (
        "q_046", "bangla",
        "DevPilot উত্তর তৈরির জন্য কোন লার্জ ল্যাঙ্গুয়েজ মডেল ব্যবহার করে?",
        ["chunk_bn_llm_01"],
        "গ্রক বা ওপেনএআই সামঞ্জস্যপূর্ণ এন্ডপয়েন্টে gpt-oss-20b মডেল গ্রাউন্ডেড উত্তর তৈরির জন্য ব্যবহৃত হয়।",
    ),
    (
        "q_047", "bangla",
        "ভেক্টর এমবেডিংয়ের জন্য কোন বহুভাষিক মডেল এবং ভেক্টর ডাইমেনশন ব্যবহৃত হয়?",
        ["chunk_bn_embedding_01"],
        "paraphrase-multilingual-MiniLM-L12-v2 মডেলের মাধ্যমে ৩৮৪-ডাইমেনশনের ডেনস ভেক্টর তৈরি করা হয়।",
    ),
    (
        "q_048", "bangla",
        "এআই জেনারেটেড উত্তরে হ্যালুসিনেশন শনাক্ত করতে কোন মেট্রিক ও থ্রেশহোল্ড ব্যবহৃত হয়?",
        ["chunk_bn_hallucination_01"],
        "আনসাপোর্টেড ক্লেইম রেট মেট্রিক্সে রেফারেন্স চাঙ্কের টোকেন মিল ৪০% এর কম হলে তা হ্যালুসিনেশন গণ্য হয়।",
    ),
    (
        "q_049", "bangla",
        "রি-র‍্যাংকিংয়ের জন্য কোন ক্রস-এনকোডার মডেল ব্যবহার করা হয়?",
        ["chunk_bn_rerank_01"],
        "ক্রস-এনকোডার রি-র‍্যাংকিংয়ের জন্য cross-encoder/ms-marco-MiniLM-L-6-v2 মডেল ব্যবহার করা হয়।",
    ),
    (
        "q_050", "bangla",
        "ট্রান্সফরমার রি-র‍্যাঙ্কার ব্যর্থ হলে সিস্টেম কী ফ্যালব্যাক আচরণ প্রদর্শন করে?",
        ["chunk_bn_rerank_fallback_01"],
        "সিস্টেম RERANKER_FALLBACK_ACTIVE ওয়ার্নিং লগ করে এবং লেক্সিক্যাল হিউরিস্টিক পদ্ধতিতে স্কোরিং করে।",
    ),
    (
        "q_051", "bangla",
        "ডাটাবেস স্কিমা আপগ্রেড করতে অ্যালেমবিকের কোন কমান্ডটি চালানো হয়?",
        ["chunk_bn_alembic_01"],
        "ডাটাবেস স্কিমা আপগ্রেড করার জন্য 'alembic upgrade head' কমান্ড ব্যবহার করা হয়।",
    ),
    (
        "q_052", "bangla",
        "পোস্টগ্রেস ডাটাবেস সংযোগে পুল সাইজ এবং ম্যাক্সিমাম ওভারফ্লো কত রাখা হয়েছে?",
        ["chunk_bn_db_pool_01"],
        "ডাটাবেস কানেকশন পুলে স্ট্যান্ডার্ড সাইজ ১০ এবং সর্বোচ্চ ওভারফ্লো ২০ নির্ধারিত থাকে।",
    ),
    (
        "q_053", "bangla",
        "এজেন্ট টাস্কের SEARCH এবং INSPECT অপারেশনের জন্য টাইমআউট লিমিট কত?",
        ["chunk_bn_timeout_01"],
        "SEARCH টাস্কের জন্য সর্বোচ্চ ১০.০ সেকেন্ড এবং INSPECT টাস্কের জন্য সর্বোচ্চ ৫.০ সেকেন্ড সময় বরাদ্দ থাকে।",
    ),
    (
        "q_054", "bangla",
        "এজেন্ট ওয়ার্কফ্লোতে ইনফিনিট লুপ ঠেকাতে সর্বোচ্চ কতটি ইটারেশন সীমা নির্ধারণ করা হয়েছে?",
        ["chunk_bn_loop_cap_01"],
        "ইনফিনিট লুপ প্রতিরোধে সর্বোচ্চ ৫টি ইটারেশন (max_iterations=5) নির্ধারণ করা হয়েছে।",
    ),
    (
        "q_055", "bangla",
        "ডুপ্লিকেট ফাইল শনাক্তকরণ এবং কন্টেন্ট ভেরিফিকেশনে কোন অ্যালগরিদম ব্যবহৃত হয়?",
        ["chunk_bn_sha256_01"],
        "ফাইলের সত্যতা ও ডুপ্লিকেট রোধে লোকাল স্টোরেজ সার্ভিস SHA-256 হ্যাশ ডাইজেস্ট হিসাব করে।",
    ),
    (
        "q_056", "bangla",
        "কোম্পানির পলিসি অনুযায়ী সফটওয়্যার ইঞ্জিনিয়াররা বছরে কত দিন বার্ষিক ও অসুস্থতাজনিত ছুটি পান?",
        ["chunk_bn_leave_01"],
        "ইঞ্জিনিয়াররা বছরে ২০ দিন বার্ষিক ছুটি এবং ১০ দিন পেইড মেডিকেল ছুটি পেয়ে থাকেন।",
    ),
    (
        "q_057", "bangla",
        "হোম অফিস এবং হাইব্রিড কাজের ক্ষেত্রে কোম্পানির সাপ্তাহিক নিয়ম কী?",
        ["chunk_bn_remote_01"],
        "প্রকৌশলীরা সপ্তাহে ৩ দিন হোম অফিস এবং ২ দিন অফিসে কাজ করার হাইব্রিড মডেল অনুসরণ করেন।",
    ),
    (
        "q_058", "bangla",
        "প্রোডাকশন শাখায় পুল রিকোয়েস্ট মার্জ করার আগে কী কী শর্ত পূরণ করতে হয়?",
        ["chunk_bn_code_review_01"],
        "কমপক্ষে দুইজন সিনিয়র ডেভেলপারের অ্যাপ্রুভাল এবং ১০০% টেস্ট পাস নিশ্চিত করতে হয়।",
    ),
    (
        "q_059", "bangla",
        "মারাত্মক প্রোডাকশন ইনসিডেন্ট (P0) ঘটলে অন-কল টিমের সর্বোচ্চ প্রতিক্রিয়া সময় (SLA) কত?",
        ["chunk_bn_sla_01"],
        "P0 গুরুতর ইনসিডেন্ট দেখা দিলে অন-কল টিমকে ১৫ মিনিটের মধ্যে প্রতিক্রিয়া জানাতে হয়।",
    ),
    (
        "q_060", "bangla",
        "নিরাপত্তা নিশ্চিত করতে এপিআই কি এবং অ্যাকাউন্টের পাসওয়ার্ড কত দিন পর পর পরিবর্তন করা আবশ্যক?",
        ["chunk_bn_security_rotation_01"],
        "সমস্ত এপিআই কি ও পাসওয়ার্ড প্রতি ৯০ দিন অন্তর পরিবর্তন করা বাধ্যতামূলক।",
    ),
    (
        "q_061", "bangla",
        "নতুন পাইথন মডিউল ও এপিআই এন্ডপয়েন্ট তৈরির ক্ষেত্রে টেকনিক্যাল ডকুমেন্টেশনের নিয়ম কী?",
        ["chunk_bn_docs_01"],
        "প্রতিটি এন্ডপয়েন্ট ও মডিউলে পূর্ণাঙ্গ ডকস্ট্রিং, প্যারামিটার বিবরণ এবং টাইপ অ্যানোটেশন থাকা বাধ্যতামূলক।",
    ),
    (
        "q_062", "bangla",
        "নতুন ডেভেলপার অনবোর্ডিংয়ের প্রথম সপ্তাহে কোম্পানি কী সুবিধা প্রদান করে?",
        ["chunk_bn_onboarding_01"],
        "নতুন যোগদানকারীদের একজন ডেডিকেটেড মেন্টর এবং লোকাল এনভায়রনমেন্ট সেটআপে সহায়তা দেওয়া হয়।",
    ),
    (
        "q_063", "bangla",
        "সিআই পাইপলাইনে কোড মার্জের পূর্বশর্ত হিসেবে ন্যূনতম কত শতাংশ টেস্ট কভারেজ প্রয়োজন?",
        ["chunk_bn_ci_01"],
        "স্বয়ংক্রিয় সিআই পাইপলাইনে ন্যূনতম ৮০% টেস্ট কোড কভারেজ বজায় রাখা আবশ্যক।",
    ),
    (
        "q_064", "bangla",
        "নতুন কোনো থার্ড-পার্টি লাইব্রেরি যুক্ত করতে কোন ওপেন সোর্স লাইসেন্স কমপ্লায়েন্স প্রয়োজন?",
        ["chunk_bn_license_01"],
        "নতুন লাইব্রেরি যুক্ত করার পূর্বে তা Apache 2.0 অথবা MIT লাইসেন্সভুক্ত হওয়া আবশ্যক।",
    ),
    (
        "q_065", "bangla",
        "ডাটাবেসের ব্যাকআপ কত সময় পর পর নেওয়া হয় এবং ব্যাকআপ স্ন্যাপশট কত দিন সংরক্ষিত থাকে?",
        ["chunk_bn_backup_01"],
        "ডাটাবেসের স্বয়ংক্রিয় ব্যাকআপ প্রতিদিন মধ্যরাতে নেওয়া হয় এবং তা ৩০ দিন সংরক্ষিত থাকে।",
    ),
    (
        "q_066", "bangla",
        "টিমের অভ্যন্তরীণ দ্রুত যোগাযোগ এবং দীর্ঘমেয়াদী সিদ্ধান্তের জন্য কোন কোন মাধ্যম ব্যবহার করা হয়?",
        ["chunk_bn_comms_01"],
        "দৈনন্দিন আপডেটের জন্য স্ল্যাক চ্যানেল এবং দীর্ঘমেয়াদী আর্কিটেকচারাল সিদ্ধান্তের জন্য RFC নথি ব্যবহৃত হয়।",
    ),
    (
        "q_067", "bangla",
        "প্রকৌশলীদের বার্ষিক পারফরম্যান্স রিভিউ কোন মাসে এবং কোন বিষয়গুলোর ওপর ভিত্তি করে অনুষ্ঠিত হয়?",
        ["chunk_bn_appraisal_01"],
        "ডিসেম্বর মাসে কোড কোয়ালিটি, সিস্টেম আর্কিটেকচার অবদান এবং টিম সহযোগিতার ওপর বার্ষিক রিভিউ হয়।",
    ),

    # =========================================================================
    # SLICE 3: ROMANIZED BANGLISH (33 Queries: q_068 to q_100)
    # =========================================================================
    (
        "q_068", "banglish",
        "DevPilot a hybrid search kivabe dense ar bm25 ke combine kore?",
        ["chunk_bng_hybrid_01"],
        "Hybrid search dense vector similarity ar BM25 Okapi ke Reciprocal Rank Fusion (k=60) diye combine kore.",
    ),
    (
        "q_069", "banglish",
        "DevPilot e file upload er max size limit koto ar boro file dile ki error ashbe?",
        ["chunk_bng_upload_01"],
        "Max file upload limit holo 10MB; er beshi hole HTTP 413 Payload Too Large error return kore.",
    ),
    (
        "q_070", "banglish",
        "DevPilot API call korte kon header ta lagbe ar ota chara call dile ki error dey?",
        ["chunk_bng_auth_01"],
        "API call korte X-API-Key header lage; missing thakle HTTP 401 Unauthorized error ashbe.",
    ),
    (
        "q_071", "banglish",
        "Onno project er data access korar try korle kon HTTP error code pawa jabe?",
        ["chunk_bng_tenant_01"],
        "Cross-tenant access e verify_project_tenant_access fail kore HTTP 403 Forbidden return kore.",
    ),
    (
        "q_072", "banglish",
        "Config file e default CHUNK_SIZE ar CHUNK_OVERLAP koto character set kora thake?",
        ["chunk_bng_config_01"],
        "Config file e CHUNK_SIZE 512 characters ar CHUNK_OVERLAP 64 characters set kora thake.",
    ),
    (
        "q_073", "banglish",
        "DevPilot vector embeddings er jonno kon multilingual model ar dimensions use kore?",
        ["chunk_bng_embedding_01"],
        "DevPilot sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 model use kore 384 dimensions er vector banay.",
    ),
    (
        "q_074", "banglish",
        "Top search candidate chunk gulo re-evaluate korte kon cross-encoder model use hoy?",
        ["chunk_bng_rerank_01"],
        "Candidate re-ranking er jonno cross-encoder/ms-marco-MiniLM-L-6-v2 model use kora hoy.",
    ),
    (
        "q_075", "banglish",
        "Cross-encoder load na hole reranker ki warning log kore ar kivabe rank kore?",
        ["chunk_bng_fallback_01"],
        "Reranker warning log kore 'RERANKER_FALLBACK_ACTIVE' ar lexical term overlap heuristic diye rank kore.",
    ),
    (
        "q_076", "banglish",
        "AI answer e hallucination check korte token overlap threshold koto dhora hoy?",
        ["chunk_bng_hallucination_01"],
        "Unsupported claims rate metric e token overlap 40% (0.40) er kom hole hallucinated dhora hoy.",
    ),
    (
        "q_077", "banglish",
        "ProcessingJob er status gulo ki ki hote pare?",
        ["chunk_bng_jobs_01"],
        "ProcessingJob er status gulo holo PENDING, IN_PROGRESS, COMPLETED, ar FAILED.",
    ),
    (
        "q_078", "banglish",
        "Database schema upgrade korte kon alembic command ta run kora lage?",
        ["chunk_bng_alembic_01"],
        "Database schema upgrade korte 'alembic upgrade head' command run korte hoy.",
    ),
    (
        "q_079", "banglish",
        "Duplicate file identify korar jonno LocalStorageService kon hash algorithm use kore?",
        ["chunk_bng_sha256_01"],
        "Duplicate check korte file content theke hexadecimal SHA-256 digest hash banano hoy.",
    ),
    (
        "q_080", "banglish",
        "Document ingestion kivabe request loop block na kore asynchronous vabe kaj kore?",
        ["chunk_bng_background_01"],
        "FastAPI BackgroundTasks use kore independent database session e text extraction ar chunking kora hoy.",
    ),
    (
        "q_081", "banglish",
        "PDF file theke text porhar jonno python er kon package use kora hoy?",
        ["chunk_bng_pdf_01"],
        "PDF parsing er jonno pypdf package er PdfReader class use kora hoy.",
    ),
    (
        "q_082", "banglish",
        "DevPilot agent workflow e 4 ta fixed phase ki ki sequence e execute hoy?",
        ["chunk_bng_agent_fsm_01"],
        "Agent workflow 4 ta phase e chole: SEARCH -> INSPECT -> SUMMARIZE -> PROPOSE.",
    ),
    (
        "q_083", "banglish",
        "GuardedToolDispatcher e malformed tool input ashle ki error status return hoy?",
        ["chunk_bng_firewall_01"],
        "Malformed input ashle Pydantic firewall ToolExecutionStatus.VALIDATION_ERROR return kore.",
    ),
    (
        "q_084", "banglish",
        "SEARCH ar INSPECT tool er per-tool timeout koto seconds kore deya ache?",
        ["chunk_bng_timeout_01"],
        "SEARCH tool er timeout 10.0 seconds ar INSPECT tool er timeout 5.0 seconds.",
    ),
    (
        "q_085", "banglish",
        "Agent run korar shomoy loop cap maximum koyta iteration execute hote pare?",
        ["chunk_bng_loop_cap_01"],
        "Agent loop cap maximum 5 ta iterations (max_iterations=5) execute hote pare.",
    ),
    (
        "q_086", "banglish",
        "Agent workflow run korar authenticated API endpoint er URL path ki?",
        ["chunk_bng_endpoint_01"],
        "Agent endpoint holo POST /api/v1/projects/{project_id}/agent/workflow.",
    ),
    (
        "q_087", "banglish",
        "WorkflowReport model e ki ki return kora hoy execution sesh hole?",
        ["chunk_bng_report_01"],
        "WorkflowReport e final_proposal, phase_history, tool_call_log, iteration count ar duration thake.",
    ),
    (
        "q_088", "banglish",
        "PostgreSQL connection pool er size ar max overflow koto configure kora ache?",
        ["chunk_bng_db_pool_01"],
        "Connection pool e normal size 10 connections ar max overflow 20 connections set kora ache.",
    ),
    (
        "q_089", "banglish",
        "Upload endpoint e kon kon file extension allowed ar onno format dile ki hoy?",
        ["chunk_bng_extensions_01"],
        "Allowed extensions holo .pdf, .md, .txt, .py; onno format dile HTTP 400 Bad Request ashbe.",
    ),
    (
        "q_090", "banglish",
        "LLM calling er jonno kon client ar default model use kora hoy?",
        ["chunk_bng_llm_client_01"],
        "OpenAI compatible async client e default model openai/gpt-oss-20b use kora hoy.",
    ),
    (
        "q_091", "banglish",
        "Bangla ar Banglish text word boundary tokenize korte kon regex pattern use hoy?",
        ["chunk_bng_tokenizer_01"],
        "Tokenizer e r'[\\w\\u0980-\\u09ff\\u200c\\u200d]+' regex pattern use hoy.",
    ),
    (
        "q_092", "banglish",
        "Lexical search e bar bar index build na korte BM25 index kivabe cache kora hoy?",
        ["chunk_bng_bm25_cache_01"],
        "BM25 index memory te cache kora hoy project_id ba corpus hash key banaye.",
    ),
    (
        "q_093", "banglish",
        "Company policy onujayi developers ra bochore koydin vacation ar sick leave pay?",
        ["chunk_bng_leave_01"],
        "Engineers ra bochore 20 din annual vacation ar 10 din paid medical sick leave pay.",
    ),
    (
        "q_094", "banglish",
        "Hybrid work policy te shoptah e koydin office ar koydin home office kora lage?",
        ["chunk_bng_remote_01"],
        "Hybrid policy te shoptah e 3 din work from home ar 2 din office kora mandatory.",
    ),
    (
        "q_095", "banglish",
        "Production e pull request merge korte minimum koyjon senior dev er approval dorkar?",
        ["chunk_bng_pr_01"],
        "PR merge korar jonno minimum 2 jon senior dev er approval ar 100% test pass dorkar.",
    ),
    (
        "q_096", "banglish",
        "P0 production incident er acknowledgment SLA koto minute er moddhe?",
        ["chunk_bng_incident_01"],
        "P0 incident er acknowledgment SLA holo maximum 15 minutes er moddhe response kora.",
    ),
    (
        "q_097", "banglish",
        "Security maintain korte developer accounts er password ar API key koydin por por change kora lage?",
        ["chunk_bng_rotation_01"],
        "Password ar API key shobai ke proti 90 days por por rotate ba change korte hoy.",
    ),
    (
        "q_098", "banglish",
        "GitHub Actions CI pipeline pass hote minimum koto percent test coverage thaka lage?",
        ["chunk_bng_ci_01"],
        "CI pipeline pass hote minimum 80% test code coverage maintain korte hobe.",
    ),
    (
        "q_099", "banglish",
        "Production database backup koto shomoy por por auto save hoy ar koydin thake?",
        ["chunk_bng_backup_01"],
        "Database backup protidin midnight e auto save hoy ar 30 days porjonto cloud e thake.",
    ),
    (
        "q_100", "banglish",
        "DevPilot local docker container build ar run korte kon command use kora hoy?",
        ["chunk_bng_docker_01"],
        "Docker container build ar run korte 'docker compose up --build' command use kora hoy.",
    ),
]


# -----------------------------------------------------------------------------
# 3. BUILD BENCHMARK DATASET WITH PRE-COMPUTED EMBEDDINGS
# -----------------------------------------------------------------------------
async def main() -> None:
    print(f"Starting benchmark dataset compilation for {len(QUERIES_DATA)} queries...")
    embedding_service = get_embedding_service()

    # Pre-embed all corpus chunks
    all_chunk_ids = list(CORPUS_CHUNKS.keys())
    all_chunk_contents = [CORPUS_CHUNKS[k]["content"] for k in all_chunk_ids]

    print(f"Generating 384-d dense embeddings for {len(all_chunk_ids)} unique corpus chunks...")
    chunk_vectors = await embedding_service.generate_embeddings(all_chunk_contents)

    for cid, vec in zip(all_chunk_ids, chunk_vectors):
        CORPUS_CHUNKS[cid]["embedding"] = vec

    # Also embed general distractors
    distractor_contents = [d["content"] for d in DISTRACTORS]
    distractor_vectors = await embedding_service.generate_embeddings(distractor_contents)
    for d, vec in zip(DISTRACTORS, distractor_vectors):
        d["embedding"] = vec

    all_records = []
    lang_counts = {"english": 0, "bangla": 0, "banglish": 0}

    for idx, (qid, lang, query, gt_ids, ref_ans) in enumerate(QUERIES_DATA, start=1):
        lang_counts[lang] += 1

        # Candidate corpus: ground truth chunk(s) + rotating language-matched distractors + 1 general distractor
        candidate_chunks = []
        for g_id in gt_ids:
            if g_id in CORPUS_CHUNKS:
                candidate_chunks.append(dict(CORPUS_CHUNKS[g_id]))

        # Select 3 distractors from same language group if possible
        lang_pool = [
            CORPUS_CHUNKS[k] for k in all_chunk_ids
            if k not in gt_ids and (
                (lang == "english" and k.startswith("chunk_en_")) or
                (lang == "bangla" and k.startswith("chunk_bn_")) or
                (lang == "banglish" and k.startswith("chunk_bng_"))
            )
        ]
        if not lang_pool:
            lang_pool = [CORPUS_CHUNKS[k] for k in all_chunk_ids if k not in gt_ids]

        for d_i in range(3):
            cand = lang_pool[(idx * 3 + d_i) % len(lang_pool)]
            if cand["chunk_id"] not in [c["chunk_id"] for c in candidate_chunks]:
                candidate_chunks.append(dict(cand))

        # Add 1 cross-lingual distractor
        other_pool = [
            CORPUS_CHUNKS[k] for k in all_chunk_ids
            if k not in gt_ids and cand["chunk_id"] not in [c["chunk_id"] for c in candidate_chunks]
        ]
        if other_pool:
            candidate_chunks.append(dict(other_pool[(idx * 7) % len(other_pool)]))

        # Add 1 general distractor (weather, recipe, sports, etc.)
        gen_d = DISTRACTORS[idx % len(DISTRACTORS)]
        if gen_d["chunk_id"] not in [c["chunk_id"] for c in candidate_chunks]:
            candidate_chunks.append(dict(gen_d))

        record = {
            "query_id": qid,
            "language": lang,
            "query": query,
            "ground_truth_chunk_ids": gt_ids,
            "reference_answer": ref_ans,
            "corpus": candidate_chunks,
        }
        all_records.append(record)

    out_file = PROJECT_ROOT / "benchmarks" / "multilingual_gold_100.jsonl"
    out_file.parent.mkdir(parents=True, exist_ok=True)

    with open(out_file, "w", encoding="utf-8") as f:
        for r in all_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"\n[SUCCESS] Successfully compiled {len(all_records)} queries to: {out_file}")
    print(f"Language distribution: {lang_counts}")
    print(f"File size: {out_file.stat().st_size / 1024 / 1024:.2f} MB")

    # Verification: Read back and assert schema compliance
    with open(out_file, "r", encoding="utf-8") as f:
        read_records = [json.loads(line) for line in f if line.strip()]

    assert len(read_records) == 100, f"Expected 100 records, got {len(read_records)}"
    for r in read_records:
        assert "query_id" in r
        assert r["language"] in ("english", "bangla", "banglish")
        assert "query" in r and len(r["query"]) > 5
        assert "ground_truth_chunk_ids" in r and len(r["ground_truth_chunk_ids"]) >= 1
        assert "reference_answer" in r and len(r["reference_answer"]) > 5
        assert "corpus" in r and len(r["corpus"]) >= 3
        # Ensure ground truth chunk is present in candidate corpus
        c_ids = [c["chunk_id"] for c in r["corpus"]]
        for gt in r["ground_truth_chunk_ids"]:
            assert gt in c_ids, f"Ground truth chunk {gt} not in candidate corpus for {r['query_id']}"

    print("[SUCCESS] All 100 items verified for schema and ground-truth consistency!")


if __name__ == "__main__":
    asyncio.run(main())
