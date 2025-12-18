from pathlib import Path
import sys
import pytest

# Ensure repository root is on sys.path so "app" can be imported when pytest
# runs from different working directories.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
BASE_DIR = Path(__file__).resolve().parent.parent


def _post_sample(filename: str, content_type: str = "application/dxf", unit: str = "millimeters"):
    sample_path = BASE_DIR / "samples" / filename
    with sample_path.open("rb") as f:
        files = {"file": (filename, f, content_type)}
        data = {"unit": unit}
        return client.post("/api/dxf/parse", files=files, data=data)


def _render_sample(filename: str, content_type: str = "application/dxf", unit: str = "millimeters"):
    sample_path = BASE_DIR / "samples" / filename
    with sample_path.open("rb") as f:
        files = {"file": (filename, f, content_type)}
        data = {"unit": unit}
        return client.post("/api/dxf/render", files=files, data=data)


def _measure_sample(filename: str, content_type: str = "application/dxf", unit: str = "millimeters"):
    sample_path = BASE_DIR / "samples" / filename
    with sample_path.open("rb") as f:
        files = {"file": (filename, f, content_type)}
        data = {"unit": unit}
        return client.post("/api/dxf/render/metrics", files=files, data=data)


def _require_rendering_deps():
    pytest.importorskip(
        "matplotlib",
        reason="Rendering requires matplotlib; install rendering extras to run.",
    )
    pytest.importorskip(
        "PIL",
        reason="Rendering requires Pillow; install rendering extras to run.",
    )


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


def test_invalid_unit_rejected():
    sample_path = BASE_DIR / "samples" / "simple_line.dxf"
    with sample_path.open("rb") as f:
        files = {"file": ("simple_line.dxf", f, "application/dxf")}
        response = client.post(
            "/api/dxf/parse",
            files=files,
            data={"unit": "yards"},
        )

    assert response.status_code == 422
    assert "centimeters" in str(response.json()["detail"])


def test_invalid_dxf_rejected():
    files = {"file": ("bad.dxf", b"not a dxf", "application/dxf")}
    response = client.post("/api/dxf/parse", files=files, data={"unit": "millimeters"})
    assert response.status_code == 400
    assert "Invalid DXF file" in response.json()["detail"]


def test_empty_upload_rejected():
    files = {"file": ("empty.dxf", b"", "application/dxf")}
    response = client.post("/api/dxf/parse", files=files, data={"unit": "millimeters"})
    assert response.status_code == 400
    assert "Uploaded file is empty" in response.json()["detail"]


def test_measurements_report_max_width_and_length_in_dual_units():
    response = _measure_sample("simple_line.dxf")
    assert response.status_code == 200
    payload = response.json()

    assert pytest.approx(payload["width_mm"], rel=1e-3) == 10.0
    assert pytest.approx(payload["length_mm"], rel=1e-3) == 0.0
    assert pytest.approx(payload["width_in"], rel=1e-3) == 10.0 / 25.4
    assert pytest.approx(payload["length_in"], abs=1e-6) == 0.0
    assert pytest.approx(payload["square_inches"], abs=1e-6) == 0.0


def test_measurements_respect_user_unit_override():
    response = _measure_sample("simple_line.dxf", unit="inches")
    assert response.status_code == 200
    payload = response.json()

    assert pytest.approx(payload["width_in"], rel=1e-3) == 10.0
    assert pytest.approx(payload["width_mm"], rel=1e-3) == 254.0
    assert payload["source_units"].lower().startswith("inch")
    assert pytest.approx(payload["square_inches"], abs=1e-6) == 0.0


def test_square_inches_calculated_from_dimensions():
    response = _measure_sample("simple_circle.dxf")
    assert response.status_code == 200
    payload = response.json()

    assert payload["width_mm"] > 0
    assert payload["length_mm"] > 0
    expected_in_from_mm = payload["width_mm"] / 25.4
    assert pytest.approx(payload["width_in"], rel=1e-3) == expected_in_from_mm
    assert pytest.approx(payload["length_in"], rel=1e-3) == payload["length_mm"] / 25.4
    assert pytest.approx(payload["square_inches"], rel=1e-6) == pytest.approx(
        payload["width_in"] * payload["length_in"], rel=1e-6
    )


def test_render_returns_png_for_valid_file():
    _require_rendering_deps()
    response = _render_sample("simple_line.dxf")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    content = response.content
    assert content.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(content) > 100


def test_render_rejects_invalid_content_type():
    _require_rendering_deps()
    response = _render_sample("simple_line.dxf", content_type="text/plain")
    assert response.status_code == 400
    assert "Unsupported file type" in response.json()["detail"]
