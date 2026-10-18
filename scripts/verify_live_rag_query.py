import os
import sqlite3
import httpx
import json
import re
import sys
from pathlib import Path
# Ensure project root is on PYTHONPATH for relative imports
sys.path.append(str(Path(__file__).resolve().parents[1]))
from src.main import app

DB_PATH = os.path.abspath('devpilot.db')
FASTAPI_URL = 'http://127.0.0.1:8000'

def hyphenate_uuid(hex_uuid: str) -> str:
    # Ensure 32 chars
    h = hex_uuid.replace('-', '')
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"

def get_latest_chunk():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('SELECT project_id, content FROM document_chunks ORDER BY created_at DESC LIMIT 1')
    row = cur.fetchone()
    conn.close()
    if not row:
        raise RuntimeError('No chunks found in the database')
    proj_id_raw, content = row
    # proj_id may be stored as raw hex string without hyphens
    proj_id = hyphenate_uuid(proj_id_raw) if '-' not in proj_id_raw else proj_id_raw
    return proj_id, content

import asyncio

def main():
    project_id, chunk_content = get_latest_chunk()
    print('Latest chunk project_id:', project_id)
    print('Chunk content:', chunk_content)

    # Formulate a question based on the chunk content
    question = 'What is the guest Wi-Fi SSID and access key?'
    print('Prompt sent to LLM:', question)

    endpoint = f"/api/v1/projects/{project_id}/rag"
    payload = {"query": question, "top_k": 3}

    async def call_endpoint():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.post(endpoint, json=payload, timeout=30.0)
            return resp

    try:
        response = asyncio.run(call_endpoint())
    except Exception as e:
        print('Error contacting RAG endpoint:', e)
        return

    print('HTTP status code:', response.status_code)
    try:
        data = response.json()
    except Exception:
        print('Response is not JSON:', response.text)
        return
    print('Response JSON:', json.dumps(data, indent=2))

    # Verify chunks_evaluated > 0
    chunks_eval = data.get('chunks_evaluated')
    answer = data.get('answer', '')
    citations = data.get('citations', [])
    if chunks_eval and chunks_eval > 0:
        print('[PASS] chunks_evaluated > 0')
    else:
        print('[FAIL] chunks_evaluated is not > 0')
    # Verify answer contains citation brackets like [1]
    if answer and re.search(r"\[\d+\]", answer):
        print('[PASS] Answer includes citation brackets')
    else:
        print('[INFO] Answer without citation brackets: ' + answer.encode('ascii', 'replace').decode('ascii'))
    if citations:
        print(f'[PASS] Extracted {len(citations)} citation sources')
    else:
        print('[INFO] No citations parsed')
    safe_answer = answer.encode('ascii', 'replace').decode('ascii')
    print('Final synthesized answer:', safe_answer)

if __name__ == '__main__':
    main()
