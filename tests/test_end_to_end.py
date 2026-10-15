"""Both services running, talking real A2A over HTTP."""
import asyncio

from demo import run, running_services


def test_request_pause_bad_edit_approve_report():
    with running_services():
        report = asyncio.run(run(send_bad_edit=True, ask=False))
    assert report.startswith("Market sizing:")
    assert "[research_value]" in report
