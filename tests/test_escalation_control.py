"""Prove the pause/cede-control/resume mechanism actually blocks and resumes, using the real file-based control-transfer seam (no LLM/browser needed)."""
import threading
import time

from capability_agent.escalation import operator_cli
from capability_agent.escalation.control import EscalationContext, EscalationTimeout, SessionControl


def test_request_intervention_blocks_until_operator_resumes(tmp_path):
    control = SessionControl(run_id="r1", run_dir=tmp_path, poll_interval_s=0.1, max_wait_s=5)
    context = EscalationContext(run_id="r1", goal="test goal", step_id=3, reason="stuck")

    def operator_after_delay():
        time.sleep(0.3)
        assert control.is_pending()
        operator_cli.resume(tmp_path, note="handled it manually")

    thread = threading.Thread(target=operator_after_delay)
    thread.start()
    started = time.monotonic()
    result = control.request_intervention(context)
    elapsed = time.monotonic() - started

    thread.join()
    assert elapsed >= 0.25
    assert result["resume_note"]["note"] == "handled it manually"
    assert not (tmp_path / "intervention.json").exists()


def test_request_intervention_times_out_without_an_operator(tmp_path):
    control = SessionControl(run_id="r2", run_dir=tmp_path, poll_interval_s=0.05, max_wait_s=0.2)
    context = EscalationContext(run_id="r2", goal="test goal", step_id=1, reason="stuck")
    try:
        control.request_intervention(context)
        assert False, "expected EscalationTimeout"
    except EscalationTimeout:
        pass


def test_operator_status_reports_no_pending_intervention_by_default(tmp_path):
    assert operator_cli.show_status(tmp_path) is None


def test_human_action_listener_records_navigation_on_the_main_frame(tmp_path):
    from unittest.mock import MagicMock

    fake_page = MagicMock()
    control = SessionControl(run_id="r3", run_dir=tmp_path, page=fake_page)
    detach = control._attach_human_action_listeners()
    on_nav = fake_page.on.call_args.args[1]

    main_frame = MagicMock(url="http://x/main")
    fake_page.main_frame = main_frame
    on_nav(main_frame)
    on_nav(MagicMock(url="http://x/iframe"))

    assert control.human_actions == [{"type": "navigation", "url": "http://x/main"}]
    detach()
    fake_page.remove_listener.assert_called_once_with("framenavigated", on_nav)
