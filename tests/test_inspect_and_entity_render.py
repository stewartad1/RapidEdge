from fastapi.testclient import TestClient
from app.main import app
from pathlib import Path
from PIL import Image
from io import BytesIO

client = TestClient(app)


def test_inspect_endpoint_reports_counts():
    with open(Path("samples") / "YourFav.dxf", "rb") as f:
        files = {"file": ("YourFav.dxf", f, "application/octet-stream")}
        resp = client.post("/api/dxf/inspect", files=files)
        assert resp.status_code == 200
        data = resp.json()
        assert "counts" in data
        counts = data["counts"]
        # total should equal sum of counts
        total = sum(counts.get(k, 0) for k in counts)
        assert data["number_of_pierces"] == total
        # At least one entity present in the sample
        assert len(data["entities"]) > 0


def test_render_entity_bboxes_produces_image():
    with open(Path("samples") / "YourFav.dxf", "rb") as f:
        files = {"file": ("YourFav.dxf", f, "application/octet-stream")}
        resp = client.post("/api/dxf/render/entity_bboxes", files=files)
        assert resp.status_code == 200
        img = Image.open(BytesIO(resp.content)).convert("RGBA")
        pixels = img.getdata()
        unique = { (r,g,b) for (r,g,b,a) in pixels if a>0 }
        assert len(unique) >= 2
