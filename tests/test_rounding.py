from pathlib import Path
import sys
import io
import math
import pytest

# Ensure repository root is on sys.path so "app" can be imported when pytest
# runs from different working directories.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
import ezdxf

from app.main import app

client = TestClient(app)


def test_measurement_rounds_to_three_decimals_for_inch_triangle():
    """Create an inch-based DXF triangle with side 3.21" and ensure the
    reported measurement is rounded to at most 3 decimal places and equals
    3.21 within a tight tolerance.
    """
    doc = ezdxf.new("R2010")
    # Set INSUNITS to inches
    doc.header["$INSUNITS"] = ezdxf.units.IN
    msp = doc.modelspace()

    side = 3.21
    height = math.sqrt(side ** 2 - (side / 2) ** 2)

    # Triangle with base on the X axis
    msp.add_line((0, 0), (side, 0))
    msp.add_line((side, 0), (side / 2, height))
    msp.add_line((side / 2, height), (0, 0))

    # ezdxf writes to filesystem paths reliably, so write to a temp file
    import tempfile

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".dxf")
    tmp.close()
    # ezdxf expects a file-like object for writing; open in text mode
    with open(tmp.name, "w") as fh:
        doc.write(fh)

    with open(tmp.name, "rb") as f:
        files = {"file": ("triangle.dxf", f, "application/dxf")}
        response = client.post("/api/dxf/render/metrics", files=files)
    assert response.status_code == 200
    payload = response.json()

    # Numeric equality (within a tiny tolerance) and rounding behavior
    assert pytest.approx(payload["object_width_in"], rel=1e-6) == side

    # Ensure serialized representation doesn't include floating-point artifacts
    text = str(payload["object_width_in"])
    # No more than 3 digits after decimal
    if "." in text:
        assert len(text.split(".")[-1]) <= 3

    # max_edge_length_in should capture the side length (3.21)
    assert pytest.approx(payload["max_edge_length_in"], rel=1e-6) == side
