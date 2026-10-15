"""Local demo: starts both services and plays the user. No keys, no Docker.

    python demo.py           pause, you approve (press Enter), report
    python demo.py --bad     first sends an invalid edit to show the validation loop
    python demo.py --yes     no prompts (used by the tests)
    python demo.py --running use services that are already running (docker compose up)

What you see:
  1. The user sends a request to the orchestrator.
  2. Orchestrator -> research agent (A2A). Research runs its ReAct loop, then pauses.
  3. Both tasks are TASK_STATE_INPUT_REQUIRED; the proposed assumptions are shown.
  4. The user approves on the same task id; both graphs resume from their checkpoints.
  5. TASK_STATE_COMPLETED with the report.
"""
import argparse
import asyncio
import threading
import time
from contextlib import contextmanager

import uvicorn

from common.config import settings
from orchestrator.a2a_client import send_message

REQUEST = "Size the European EV charging aftermarket"


@contextmanager
def running_services():
    """Run research agent (:8001) and orchestrator (:8000) in background threads."""
    servers = [
        uvicorn.Server(uvicorn.Config("research_agent.main:app", port=8001, log_level="warning")),
        uvicorn.Server(uvicorn.Config("orchestrator.main:app", port=8000, log_level="warning")),
    ]
    for server in servers:
        threading.Thread(target=server.run, daemon=True).start()
    while not all(server.started for server in servers):
        time.sleep(0.1)
    try:
        yield
    finally:
        for server in servers:
            server.should_exit = True


async def run(send_bad_edit: bool, ask: bool) -> str:
    url, token = settings.orchestrator_url, settings.a2a_shared_secret

    print(f"\n[1] user -> orchestrator: {REQUEST!r}")
    task = await send_message(url, token, REQUEST)
    show(task)

    if send_bad_edit:
        bad = [{**task.data["proposed"][0], "low": 99_000_000}]   # low > base
        print("\n[2] user sends an invalid edit (low > base)")
        task = await send_message(url, token, {"approved": bad}, task.task_id, task.context_id)
        show(task)

    if ask:
        input("\n    Press Enter to approve... ")
    print("\n[3] user -> orchestrator: 'approve'  (same task id, graphs resume)")
    task = await send_message(url, token, "approve", task.task_id, task.context_id)
    show(task)
    return task.data.get("report", "")


def show(task) -> None:
    print(f"    <- {task.state}  (task {task.task_id[:8]})")
    if task.state == "TASK_STATE_INPUT_REQUIRED":
        if task.data.get("error"):
            print(f"    error: {task.data['error']}")
        for row in task.data["proposed"]:
            print(f"    - {row['name']}: low {row['low']:,.0f} | base {row['base']:,.0f} | "
                  f"high {row['high']:,.0f}  [{row['source_status']}]")
    elif task.state == "TASK_STATE_COMPLETED":
        print("\n" + task.data["report"] + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bad", action="store_true", help="send an invalid edit first")
    parser.add_argument("--yes", action="store_true", help="don't wait for Enter")
    parser.add_argument("--running", action="store_true", help="use already-running services")
    args = parser.parse_args()

    if args.running:
        asyncio.run(run(args.bad, ask=not args.yes))
    else:
        with running_services():
            asyncio.run(run(args.bad, ask=not args.yes))


if __name__ == "__main__":
    main()
