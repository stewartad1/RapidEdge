from pathlib import Path
import sys
import math

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
import ezdxf

from app.main import app

client = TestClient(app)


def test_parse_triangle_counts_three_lines():
    doc = ezdxf.new("R2010")
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
        r = client.post("/api/dxf/parse", files=files)

    assert r.status_code == 200
    payload = r.json()
    assert payload["number_of_pierces"] == 3
    assert payload["number_of_lines"] == 3
    assert payload["number_of_circles"] == 0
    assert payload["number_of_arcs"] == 0
    assert payload["number_of_polylines"] == 0
