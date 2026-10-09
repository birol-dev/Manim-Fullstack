import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

# Ensure backend/ is in sys.path for all pytest runs
BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import main
from executor import ManimExecutor

# Importing the backend must not delete scratch renders or rewrite manim.cfg.
main.RUN_STARTUP_MAINTENANCE = False


class LocalClient(TestClient):
    """Talks to the app as http(s)/ws://localhost, like a browser on the same machine.

    The server refuses unknown Host headers (DNS-rebinding guard), and Starlette's
    websocket_connect otherwise always uses the host "testserver".
    """

    def websocket_connect(self, url, *args, **kwargs):
        if url.startswith("/"):
            url = f"ws://localhost{url}"
        return super().websocket_connect(url, *args, **kwargs)


@pytest.fixture
def client():
    """Reusable FastAPI TestClient fixture."""
    return LocalClient(main.app, base_url="http://localhost")


@pytest.fixture
def workspace(tmp_path):
    """Isolated temporary workspace directory with standard subfolders."""
    media_dir = tmp_path / "media"
    assets_dir = tmp_path / "assets"
    media_dir.mkdir(parents=True, exist_ok=True)
    assets_dir.mkdir(parents=True, exist_ok=True)
    return tmp_path


@pytest.fixture
def executor(workspace):
    """ManimExecutor instance configured with isolated workspace."""
    return ManimExecutor(str(workspace))
