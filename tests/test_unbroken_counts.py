from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
import ezdxf

from app.main import app

client = TestClient(app)


def test_counts_include_arcs_and_circles_and_polylines():
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()

    # add one line, one circle, one arc, and one lwpolyline
    msp.add_line((0, 0), (10, 0))
    msp.add_circle((20, 0), radius=5)
    # add arc using positional args (center, radius, start_angle, end_angle)
    msp.add_arc((40, 0), 5, 0, 90)
    # lwpolyline with 4 points
    # lwpolyline with 4 points (closed flag is optional for counting)
    msp.add_lwpolyline([(60, 0), (70, 0), (70, 10), (60, 10)])

    import tempfile
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".dxf")
    tmp.close()
    with open(tmp.name, "w") as fh:
        doc.write(fh)

    with open(tmp.name, "rb") as f:
        files = {"file": ("mix.dxf", f, "application/dxf")}
        r = client.post("/api/dxf/parse", files=files)

    assert r.status_code == 200
    payload = r.json()

    assert payload["number_of_lines"] == 1
    assert payload["number_of_circles"] == 1
    assert payload["number_of_arcs"] == 1
    assert payload["number_of_polylines"] == 1
    assert payload["number_of_pierces"] == 4
