from pathlib import Path
import sys

# Ensure repository root is on sys.path so "app" can be imported when pytest
# runs from different working directories.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
BASE_DIR = Path(__file__).resolve().parent.parent


def _post_sample(filename: str, content_type: str = "application/dxf"):
    sample_path = BASE_DIR / "samples" / filename
    with sample_path.open("rb") as f:
        files = {"file": (filename, f, content_type)}
        return client.post("/api/dxf/parse", files=files)


def test_parse_line_file_returns_entities_and_bounds():
    response = _post_sample("simple_line.dxf")
    assert response.status_code == 200
    payload = response.json()

    assert payload["metadata"]["filename"] == "simple_line.dxf"
    assert payload["metadata"]["version"]

    assert any(layer["name"] == "0" for layer in payload["layers"])

    assert len(payload["entities"]) == 1
    entity = payload["entities"][0]
    assert entity["type"] == "LINE"
    assert entity["layer"] == "0"

    bounds = payload["bounds"]
    assert bounds["min_x"] == 0
    assert bounds["max_x"] == 10
    assert bounds["min_y"] == 0
    assert bounds["max_y"] == 0


def test_parse_circle_file_returns_entities_and_bounds():
    response = _post_sample("simple_circle.dxf")
    assert response.status_code == 200
    payload = response.json()

    assert payload["metadata"]["filename"] == "simple_circle.dxf"
    assert payload["metadata"]["version"]

    assert any(layer["name"] == "0" for layer in payload["layers"])

    assert len(payload["entities"]) == 1
    entity = payload["entities"][0]
    assert entity["type"] == "CIRCLE"
    assert entity["layer"] == "0"

    bounds = payload["bounds"]
    assert bounds["min_x"] <= 5
    assert bounds["max_x"] >= 5
    assert bounds["min_y"] <= 5
    assert bounds["max_y"] >= 5


def test_invalid_content_type_rejected():
    response = _post_sample("simple_line.dxf", content_type="text/plain")
    assert response.status_code == 400
    assert "Unsupported file type" in response.json()["detail"]


def test_invalid_dxf_rejected():
    files = {"file": ("bad.dxf", b"not a dxf", "application/dxf")}
    response = client.post("/api/dxf/parse", files=files)
    assert response.status_code == 400
    assert "Invalid DXF file" in response.json()["detail"]
