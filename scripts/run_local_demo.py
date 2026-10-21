"""One-click local fallback demo runner for DevPilot.

Validates environment, applies migrations, seeds sample documents, and launches the server.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Enable ANSI color support on Windows terminals
if sys.platform == "win32":
    os.system("")

# Project paths
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Color tokens for terminal output
BOLD = "\033[1m"
GREEN = "\033[92m"
CYAN = "\033[96m"
YELLOW = "\033[93m"
RED = "\033[91m"
DIM = "\033[2m"
RESET = "\033[0m"


def print_header(title: str) -> None:
    print(f"\n{BOLD}{CYAN}{'=' * 75}{RESET}")
    print(f"{BOLD}{CYAN}  {title}{RESET}")
    print(f"{BOLD}{CYAN}{'=' * 75}{RESET}\n")


def print_step(step_num: int, message: str) -> None:
    print(f"{BOLD}{GREEN}[Step {step_num}]{RESET} {message}")


def check_python_version() -> None:
    """Ensure Python version is 3.11 or higher."""
    if sys.version_info < (3, 11):
        print(f"{RED}Error: DevPilot requires Python 3.11+ (Detected: {sys.version}){RESET}")
        sys.exit(1)


def ensure_env_file() -> None:
    """Ensure a .env file exists, copying from .env.example if missing."""
    env_file = PROJECT_ROOT / ".env"
    example_env = PROJECT_ROOT / ".env.example"

    if not env_file.exists():
        if example_env.exists():
            shutil.copy(example_env, env_file)
            print(f"  {YELLOW}Created .env from .env.example (SQLite default){RESET}")
        else:
            with open(env_file, "w", encoding="utf-8") as f:
                f.write("PROJECT_NAME=DevPilot\nVERSION=0.1.0\nDEBUG=True\nDATABASE_URL=sqlite+aiosqlite:///./devpilot.db\n")
            print(f"  {YELLOW}Initialized new .env with default settings{RESET}")
    else:
        print(f"  {DIM}Found existing .env file{RESET}")


def run_command(cmd: list[str], description: str) -> None:
    """Execute a shell command with proper error handling."""
    try:
        res = subprocess.run(cmd, cwd=PROJECT_ROOT, check=True, capture_output=True, text=True)
        if res.stdout:
            for line in res.stdout.strip().splitlines()[-3:]:
                print(f"  {DIM}{line}{RESET}")
    except subprocess.CalledProcessError as exc:
        print(f"{RED}Failed: {description}{RESET}")
        if exc.stderr:
            print(f"{RED}{exc.stderr.strip()}{RESET}")
        sys.exit(exc.returncode)


def run_migrations() -> None:
    """Apply Alembic database migrations."""
    run_command(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        "Alembic database migrations",
    )


def run_demo_seeder(force: bool = False) -> None:
    """Execute sample data seeder."""
    cmd = [sys.executable, "scripts/seed_demo.py"]
    if force:
        cmd.append("--force")
    run_command(cmd, "Demo workspace data seeding")


def print_demo_instructions(host: str, port: int) -> None:
    """Print terminal guide and sample curl commands."""
    base_url = f"http://{host}:{port}"
    print(f"\n{BOLD}{GREEN}{'=' * 75}{RESET}")
    print(f"{BOLD}{GREEN}  DevPilot Local Demo Ready & Running!{RESET}")
    print(f"{BOLD}{GREEN}{'=' * 75}{RESET}")
    print(f"  {BOLD}Local API Server  :{RESET} {CYAN}{base_url}{RESET}")
    print(f"  {BOLD}Interactive Docs  :{RESET} {CYAN}{base_url}/docs{RESET}")
    print(f"  {BOLD}Demo API Key      :{RESET} {YELLOW}demo-readonly-key{RESET} {DIM}(Read-Only Safe Mode){RESET}")
    print(f"  {BOLD}Admin/Tenant Key  :{RESET} {YELLOW}devpilot-demo-key{RESET} {DIM}(Full Access){RESET}")
    print(f"{DIM}{'-' * 75}{RESET}")
    print(f"{BOLD}Sample Evaluator Verification Commands:{RESET}\n")

    print(f"{BOLD}1. Service Health Check:{RESET}")
    print(f"   {CYAN}curl {base_url}/api/v1/health{RESET}\n")

    print(f"{BOLD}2. List Seeded Evaluation Projects (Read-Only Demo Mode):{RESET}")
    print(f"   {CYAN}curl {base_url}/api/v1/projects \\{RESET}")
    print(f"   {CYAN}  -H \"X-API-Key: demo-readonly-key\"{RESET}\n")

    print(f"{BOLD}3. Execute Grounded RAG Query with Inline Citations:{RESET}")
    print(f"   {CYAN}curl -X POST {base_url}/api/v1/projects/c651c832-a5cc-473a-abff-76f08e5e1b5f/rag \\{RESET}")
    print(f"   {CYAN}  -H \"X-API-Key: demo-readonly-key\" \\{RESET}")
    print(f"   {CYAN}  -H \"Content-Type: application/json\" \\{RESET}")
    print(f"   {CYAN}  -d '{{\"query\": \"What is the architecture of DevPilot?\"}}'{RESET}\n")

    print(f"{BOLD}4. Execute Semantic & Hybrid Search:{RESET}")
    print(f"   {CYAN}curl -X POST {base_url}/api/v1/projects/c651c832-a5cc-473a-abff-76f08e5e1b5f/search \\{RESET}")
    print(f"   {CYAN}  -H \"X-API-Key: demo-readonly-key\" \\{RESET}")
    print(f"   {CYAN}  -H \"Content-Type: application/json\" \\{RESET}")
    print(f"   {CYAN}  -d '{{\"query\": \"hybrid consensus reranker\", \"mode\": \"hybrid\"}}'{RESET}\n")

    print(f"{BOLD}5. Test Write Mutation Guard (Should return 403 Forbidden in Demo Mode):{RESET}")
    print(f"   {CYAN}curl -X POST {base_url}/api/v1/projects \\{RESET}")
    print(f"   {CYAN}  -H \"X-API-Key: demo-readonly-key\" \\{RESET}")
    print(f"   {CYAN}  -H \"Content-Type: application/json\" \\{RESET}")
    print(f"   {CYAN}  -d '{{\"name\": \"Unauthorized Mutation Project\"}}'{RESET}")
    print(f"{BOLD}{GREEN}{'=' * 75}{RESET}\n")


def start_server(host: str, port: int, reload: bool) -> None:
    """Launch Uvicorn ASGI server."""
    import uvicorn
    uvicorn.run("src.main:app", host=host, port=port, reload=reload)


def main() -> None:
    parser = argparse.ArgumentParser(description="One-click local fallback demo runner for DevPilot.")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host interface (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on (default: 8000)")
    parser.add_argument("--reload", action="store_true", default=False, help="Enable Uvicorn auto-reload")
    parser.add_argument("--force-reseed", action="store_true", default=False, help="Force re-seeding of demo workspace")
    parser.add_argument("--no-server", action="store_true", default=False, help="Run setup and seeding without starting Uvicorn")
    args = parser.parse_args()

    print_header("DevPilot Local Fallback Demo Setup & Runner")

    # Step 1: Environment check
    print_step(1, "Checking Python environment and dependencies...")
    check_python_version()
    ensure_env_file()

    # Step 2: Database migrations
    print_step(2, "Running database migrations via Alembic...")
    run_migrations()

    # Step 3: Seed sample demo documents
    print_step(3, "Seeding demo evaluation workspace and documents...")
    run_demo_seeder(force=args.force_reseed)

    # Step 4: Display instructions and commands
    print_demo_instructions(args.host, args.port)

    # Step 5: Start server
    if not args.no_server:
        print_step(4, f"Spinning up Uvicorn ASGI server at http://{args.host}:{args.port}...")
        start_server(args.host, args.port, args.reload)
    else:
        print(f"{GREEN}Setup and seeding completed successfully (--no-server specified).{RESET}")


if __name__ == "__main__":
    main()
