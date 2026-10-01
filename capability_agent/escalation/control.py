"""The pause / cede-control / resume control-transfer model for one run."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from playwright.sync_api import Page


class EscalationTimeout(Exception):
    """No operator resumed the session within the allotted wait window."""


@dataclass
class EscalationContext:
    run_id: str
    goal: str
    step_id: int
    reason: str
    screenshot_path: str | None = None
    current_url: str | None = None


@dataclass
class SessionControl:
    """Lives in the discovery/replay process; the operator CLI talks to it
    only through files on disk, so control can transfer without either side
    holding a reference to the other's process.
    """

    run_id: str
    run_dir: Path
    page: Page | None = None
    poll_interval_s: float = 1.0
    max_wait_s: float = 600.0
    human_actions: list[dict] = field(default_factory=list)

    @property
    def intervention_path(self) -> Path:
        return self.run_dir / "intervention.json"

    @property
    def resume_signal_path(self) -> Path:
        return self.run_dir / "resume.signal"

    def is_pending(self) -> bool:
        return self.intervention_path.exists() and not self.resume_signal_path.exists()

    def request_intervention(self, context: EscalationContext) -> dict:
        """Write the intervention request, wait for an operator to resume."""
        self.resume_signal_path.unlink(missing_ok=True)
        self.intervention_path.write_text(json.dumps(context.__dict__, indent=2))
        detach = self._attach_human_action_listeners()
        waited = 0.0
        while not self.resume_signal_path.exists():
            time.sleep(self.poll_interval_s)
            waited += self.poll_interval_s
            if waited >= self.max_wait_s:
                detach()
                raise EscalationTimeout(f"No operator resumed run {self.run_id} within {self.max_wait_s}s")
        detach()
        resume_note = json.loads(self.resume_signal_path.read_text())
        self.intervention_path.unlink(missing_ok=True)
        return {"resume_note": resume_note, "human_actions": self.human_actions}

    def _attach_human_action_listeners(self):
        """Keep logging what happens on the live page while a human drives it."""
        if self.page is None:
            return lambda: None

        def on_nav(frame):
            if frame == self.page.main_frame:
                self.human_actions.append({"type": "navigation", "url": frame.url})

        self.page.on("framenavigated", on_nav)
        return lambda: self.page.remove_listener("framenavigated", on_nav)
