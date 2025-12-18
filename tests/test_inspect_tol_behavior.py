from fastapi.testclient import TestClient
from app.main import app
from pathlib import Path

client = TestClient(app)


def test_join_tol_affects_connected_count():
    with open(Path("samples") / "YourFav.dxf", "rb") as f:
        files = {"file": ("YourFav.dxf", f, "application/octet-stream")}
        # default join_tol 0.0
        resp = client.post("/api/dxf/inspect", files=files)
        assert resp.status_code == 200
        data = resp.json()
        base = data["connected_pierces"]

    with open(Path("samples") / "YourFav.dxf", "rb") as f:
        files = {"file": ("YourFav.dxf", f, "application/octet-stream")}
        # Use a slightly larger tol that should merge nearby endpoints (~0.03)
        resp = client.post("/api/dxf/inspect", files=files, data={"join_tol": 0.03})
        assert resp.status_code == 200
        data2 = resp.json()

    # Expect that with larger tolerance the connected count is <= the strict count
    assert data2["connected_pierces"] <= base
    # If the file has entities separated by ~0.02, a 0.03 tol will merge at least one pair
    assert data2["connected_pierces"] < base
