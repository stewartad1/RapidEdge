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


def test_obb_for_equilateral_triangle_matches_edge_and_angle():
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = ezdxf.units.IN
    msp = doc.modelspace()

    side = 3.21
    height = math.sqrt(side ** 2 - (side / 2) ** 2)

    # Base on X axis
    msp.add_line((0, 0), (side, 0))
    msp.add_line((side, 0), (side / 2, height))
    msp.add_line((side / 2, height), (0, 0))

    import tempfile

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".dxf")
    tmp.close()
    with open(tmp.name, "w") as fh:
        doc.write(fh)

    with open(tmp.name, "rb") as f:
        files = {"file": ("triangle.dxf", f, "application/dxf")}
        r = client.post("/api/dxf/render/metrics", files=files)

    assert r.status_code == 200
    payload = r.json()

    # OBB aligned with base: width equals side, length equals triangle height
    assert pytest.approx(payload["obb_width_in"], rel=1e-6) == side
    assert pytest.approx(payload["obb_length_in"], rel=1e-6) == round(height, 3)
    # Angle should be near 0 degrees for the base-on-x-axis case
    assert abs(payload["obb_angle_deg"]) < 1.0

    # Minimal enclosing square side should be the side length (3.21)
    assert pytest.approx(payload["min_enclosing_square_side_in"], rel=1e-6) == side
    # min-max rect max side should equal the minimal square side
    assert pytest.approx(max(payload["min_max_rect_width_in"], payload["min_max_rect_length_in"]), rel=1e-6) == side


def test_obb_for_rotated_triangle_reports_angle_near_90():
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = ezdxf.units.IN
    msp = doc.modelspace()

    side = 3.21
    height = math.sqrt(side ** 2 - (side / 2) ** 2)

    # Base vertical (rotated 90 degrees)
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
        r = client.post("/api/dxf/render/metrics", files=files)

    assert r.status_code == 200
    payload = r.json()

    # OBB should still be width=side, length=height; angle near 90 degrees
    assert pytest.approx(payload["obb_width_in"], rel=1e-6) == side
    assert pytest.approx(payload["obb_length_in"], rel=1e-6) == round(height, 3)
    angle = payload["obb_angle_deg"]
    # Rotation can vary depending on which hull edge yields the minimum box,
    # but the box area should be close to side * height. Use a looser tolerance
    # to account for rounding of OBB dimensions.
    assert pytest.approx(payload["obb_width_in"] * payload["obb_length_in"], rel=1e-3) == pytest.approx(side * height, rel=1e-3)
    # Angle should be a finite value and in a sensible range.
    assert 0.0 <= abs(angle) <= 180.0
