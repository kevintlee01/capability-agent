"""Shared fixtures: a real uvicorn-served mock app on a random free port, no signal handlers (we're in a background thread)."""
import socket
import threading
import time

import pytest
import uvicorn

from mock_app.main import app


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _ServerThread(uvicorn.Server):
    def install_signal_handlers(self) -> None:
        pass


@pytest.fixture(scope="session")
def live_mock_app_url():
    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error", loop="asyncio")
    server = _ServerThread(config=config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=5)
