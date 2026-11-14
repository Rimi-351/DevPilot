"""Opt-in Selenium smoke coverage for the shipped dashboard."""

import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

ROOT = Path(__file__).resolve().parents[2]
API_KEY = "devpilot-demo-key"


@pytest.fixture(scope="session")
def ui_server(tmp_path_factory: pytest.TempPathFactory):
    """Run an isolated SQLite-backed app instance on an available local port."""
    data_dir = tmp_path_factory.mktemp("devpilot-ui")
    database = data_dir / "ui.db"
    env = os.environ.copy()
    env.update(
        {
            "DEBUG": "false",
            "DEMO_MODE": "false",
            "DATABASE_URL": f"sqlite+aiosqlite:///{database.as_posix()}",
            "TESTING": "true",
            "EMBEDDING_MOCK": "true",
            "LLM_MOCK": "true",
            "PYTHONPATH": str(ROOT),
        }
    )
    setup_code = f"""import asyncio
from src.core.database import engine, async_session_factory
from src.models.base import Base
from src.models.project import Project
from src.models.document import Document
from src.models.document_chunk import DocumentChunk
from src.models.processing_job import ProcessingJob

async def setup():
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with async_session_factory() as session:
        session.add(Project(name="UI smoke workspace", tenant_id="{API_KEY}", owner_api_key="{API_KEY}"))
        await session.commit()

asyncio.run(setup())
"""
    subprocess.run([sys.executable, "-c", setup_code], cwd=ROOT, env=env, check=True)

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "src.main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        health_url = f"http://127.0.0.1:{port}/api/v1/health"
        deadline = time.monotonic() + 10
        while True:
            try:
                with urllib.request.urlopen(health_url, timeout=1) as response:
                    if response.status == 200:
                        break
            except (urllib.error.URLError, TimeoutError):
                if time.monotonic() >= deadline:
                    raise RuntimeError("Uvicorn did not become healthy within 10 seconds")
            if time.monotonic() >= deadline:
                raise RuntimeError("Uvicorn did not become healthy within 10 seconds")
            time.sleep(0.1)
        yield f"http://127.0.0.1:{port}"
    finally:
        process.terminate()
        process.wait(timeout=10)


@pytest.fixture
def browser():
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    driver = webdriver.Chrome(options=options)
    driver.set_window_size(1365, 1000)
    yield driver
    driver.quit()


def open_dashboard(browser, base_url: str) -> WebDriverWait:
    browser.get(f"{base_url}/ui")
    return WebDriverWait(browser, 10)


@pytest.mark.ui
def test_ui_displays_title_and_bengali_hero(browser, ui_server) -> None:
    wait = open_dashboard(browser, ui_server)
    wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "main h1")))
    assert browser.title == "DevPilot - Intelligent Hybrid RAG & Semantic Search Platform"
    assert "যেকোনো কিছু জিজ্ঞাসা করুন" in browser.find_element(By.CSS_SELECTOR, "main h1").text


@pytest.mark.ui
def test_invalid_api_key_blocks_project_fetching(browser, ui_server) -> None:
    """Verify that using an invalid API key fails protected API requests from the frontend."""
    wait = open_dashboard(browser, ui_server)
    wait.until(EC.visibility_of_element_located((By.ID, "backendStatusText")))
    
    # Configure settings with invalid API key
    browser.find_element(By.CSS_SELECTOR, "button[title='System Settings']").click()
    key = browser.find_element(By.ID, "settingsApiKey")
    key.clear()
    key.send_keys("invalid-ui-key")
    browser.find_element(By.CSS_SELECTOR, "button[onclick='saveSettings()']").click()
    wait.until(EC.invisibility_of_element_located((By.ID, "settingsModal")))

    # Attempt to fetch projects via frontend script with the invalid key
    result = browser.execute_async_script(
        "const done = arguments[0];"
        "const apiKey = localStorage.getItem('devpilot_api_key') || 'invalid-ui-key';"
        "fetch('/api/v1/projects', {headers: {'X-API-Key': apiKey}})"
        ".then(async r => done({status: r.status}))"
        ".catch(err => done({error: String(err)}));"
    )
    assert result["status"] in (401, 403), f"Expected unauthorized status, got: {result}"


@pytest.mark.ui
def test_valid_key_uploads_text_document_and_shows_success(browser, ui_server, tmp_path) -> None:
    wait = open_dashboard(browser, ui_server)
    wait.until(EC.visibility_of_element_located((By.ID, "backendStatusText")))

    # 1. Configure settings with the valid API key FIRST so projects can load
    browser.find_element(By.CSS_SELECTOR, "button[title='System Settings']").click()
    wait.until(EC.visibility_of_element_located((By.ID, "settingsApiKey")))
    key = browser.find_element(By.ID, "settingsApiKey")
    key.clear()
    key.send_keys(API_KEY)
    browser.find_element(By.CSS_SELECTOR, "button[onclick='saveSettings()']").click()
    wait.until(EC.invisibility_of_element_located((By.ID, "settingsModal")))

    # 2. Now wait for project dropdown options to populate
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#uploadProjectSelect option")))

    # 3. Open upload modal and upload test file
    browser.find_element(By.CSS_SELECTOR, "button[onclick='openUploadModal()']").click()
    wait.until(EC.visibility_of_element_located((By.ID, "uploadModal")))
    sample = tmp_path / "smoke.txt"
    sample.write_text("DevPilot Selenium UI smoke upload.", encoding="utf-8")
    browser.find_element(By.ID, "uploadFileInput").send_keys(str(sample))
    browser.find_element(By.ID, "uploadSubmitBtn").click()
    
    wait.until(EC.text_to_be_present_in_element((By.ID, "uploadStatusMsg"), "smoke.txt"))
    status = browser.find_element(By.ID, "uploadStatusMsg")
    assert "smoke.txt" in status.text
    assert "bg-emerald-950" in status.get_attribute("class"), status.text

    # 4. Verify document persistence via API
    project_id = browser.find_element(By.ID, "uploadProjectSelect").get_attribute("value")
    documents = browser.execute_async_script(
        "const [projectId, apiKey, done] = arguments;"
        "fetch(`/api/v1/documents?project_id=${encodeURIComponent(projectId)}`, "
        "{headers: {'X-API-Key': apiKey}})"
        ".then(async response => done({status: response.status, body: await response.json()}))"
        ".catch(error => done({error: String(error)}));",
        project_id,
        API_KEY,
    )
    assert documents["status"] == 200, documents
    assert any(item["filename"] == "smoke.txt" for item in documents["body"]["items"])


@pytest.mark.ui
def test_health_endpoint_is_reachable_from_browser(browser, ui_server) -> None:
    wait = open_dashboard(browser, ui_server)
    health = browser.execute_async_script(
        "const done = arguments[0]; fetch('/api/v1/health')"
        ".then(r => r.json().then(body => done({status: r.status, body})))"
        ".catch(error => done({error: String(error)}));"
    )
    assert health["status"] == 200
    assert health["body"]["status"] == "healthy"