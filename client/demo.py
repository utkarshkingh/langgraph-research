"""Drive the full flow end to end so the pause/resume is visible.

Two modes:

  python client/demo.py            # in-process: runs the orchestrator graph directly
  python client/demo.py --http     # over HTTP: hits the two running FastAPI services
                                    #   (start them first; see README)

Either way you see the same three beats:
  1) invoke  -> run pauses at INPUT_REQUIRED, printing the proposed assumptions
  2) a human 'approves' them
  3) resume  -> run continues from the checkpoint and prints the final report
"""
from __future__ import annotations

import argparse
import os
import sys
import uuid

# Make the repo root importable when run as `python client/demo.py`.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

REQUEST = "Size the European EV charging aftermarket"


def run_inproc() -> None:
    from langgraph.types import Command

    from common.checkpointer import build_checkpointer
    from orchestrator.graph import build_orchestrator

    graph = build_orchestrator(build_checkpointer())
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    print(f"\n[1] invoke  (thread_id={thread_id})")
    result = graph.invoke({"request": REQUEST}, config=config)
    assert "__interrupt__" in result, "expected a human-in-the-loop pause"
    payload = result["__interrupt__"][0].value
    proposed = payload["proposed"]
    _print_proposed(proposed)

    print("[2] human approves the proposed assumptions as-is")
    print("\n--- process could stop here for hours; state is checkpointed ---\n")

    print("[3] resume")
    final = graph.invoke(Command(resume={"approved": proposed}), config=config)
    print("\n" + final["report"] + "\n")


def run_http() -> None:
    import httpx

    from common.security import auth_header

    base = "http://localhost:8080"
    thread_id = str(uuid.uuid4())

    print(f"\n[1] POST /invoke  (thread_id={thread_id})")
    r = httpx.post(
        f"{base}/invoke",
        json={"request": REQUEST, "thread_id": thread_id},
        headers=auth_header(),
        timeout=60,
    )
    r.raise_for_status()
    data = r.json()
    assert data["status"] == "input_required", data
    proposed = data["proposed"]
    _print_proposed(proposed)

    print("[2] human approves\n")
    print("[3] POST /resume")
    r = httpx.post(
        f"{base}/resume",
        json={"thread_id": thread_id, "approved": proposed},
        headers=auth_header(),
        timeout=60,
    )
    r.raise_for_status()
    print("\n" + r.json()["report"] + "\n")


def _print_proposed(proposed: list) -> None:
    print("    -> INPUT_REQUIRED. proposed assumptions:")
    for p in proposed:
        print(
            f"       - {p['name']}: base={p['base']} "
            f"[low={p['low']}, high={p['high']}] source={p['source_status']}"
        )
    print()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--http", action="store_true", help="hit the running services")
    args = ap.parse_args()
    run_http() if args.http else run_inproc()
