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


def test_parse_bounds_are_rounded_to_three_decimals():
    """Create an inch-based DXF with a base 3.21" and ensure the parse
    endpoint returns bounds rounded to at most 3 decimal places.
    """
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = ezdxf.units.IN
    msp = doc.modelspace()

    side = 3.21
    height = math.sqrt(side ** 2 - (side / 2) ** 2)

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
        response = client.post("/api/dxf/parse", files=files)

    assert response.status_code == 200
    payload = response.json()
    bounds = payload["bounds"]

    # Numeric equality
    assert bounds["max_x"] == pytest.approx(side, rel=1e-6)

    # Serialized representation does not expose more than 3 decimals
    text = str(bounds["max_x"])
    if "." in text:
        assert len(text.split(".")[-1]) <= 3
