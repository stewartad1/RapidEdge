from pathlib import Path
import sys
import math

# Ensure repository root is on sys.path so "app" can be imported when pytest
# runs from different working directories.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
import ezdxf
import pytest

from app.main import app

client = TestClient(app)


def test_rotated_triangle_reports_correct_width_in_inches():
    """Create an inch-based triangle rotated so its base is vertical and
    verify the metrics endpoint still reports the longest bounding-box
    dimension (the side length) as `width_in` (3.21)."""
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = ezdxf.units.IN
    msp = doc.modelspace()

    side = 3.21
    height = math.sqrt(side ** 2 - (side / 2) ** 2)

    # Start with base on X axis, then rotate 90 degrees by swapping coords
    # so the base becomes vertical. The bounding box extents will swap.
    msp.add_line((0, 0), (0, side))
    msp.add_line((0, side), (height, side / 2))
    msp.add_line((height, side / 2), (0, 0))

    import tempfile

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".dxf")
    tmp.close()
    with open(tmp.name, "w") as fh:
        doc.write(fh)

    with open(tmp.name, "rb") as f:
        files = {"file": ("rot_triangle.dxf", f, "application/dxf")}
        response = client.post("/api/dxf/render/metrics", files=files)

    assert response.status_code == 200
    payload = response.json()

    # object_width_in should equal side (3.21) even though the base is vertical
    assert pytest.approx(payload["object_width_in"], rel=1e-6) == side

    # Bounding box fields reflect axis extents (x_extent, y_extent)
    # Values are rounded to 3 decimals by the API, so compare to rounded values
    assert pytest.approx(payload["bbox_width_in"], rel=1e-6) == round(height, 3)
    assert pytest.approx(payload["bbox_length_in"], rel=1e-6) == round(side, 3)

    # max_edge_length should still be the side length
    assert pytest.approx(payload["max_edge_length_in"], rel=1e-6) == side
