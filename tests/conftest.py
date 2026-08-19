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


@pytest.fixture
def client():
    """Reusable FastAPI TestClient fixture."""
    return TestClient(main.app)


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
