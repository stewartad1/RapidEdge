from pathlib import Path
from app import services


def test_yourfav_render_has_multiple_colors(monkeypatch):
    """Render samples/YourFav.dxf with per-pierce coloring enabled and ensure multiple colors are present."""
    assert services.COLOR_EACH_PIERCE is True

    # Use a small deterministic palette to make color detection easier
    monkeypatch.setattr(services, "PIERCE_COLORS", [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0)])

    p = Path("samples") / "YourFav.dxf"
    png = services.render_dxf_png(str(p))

    from PIL import Image
    from io import BytesIO

    img = Image.open(BytesIO(png)).convert("RGBA")
    pixels = img.getdata()
    unique_colors = { (r,g,b) for (r,g,b,a) in pixels if a > 0 }

    # Expect at least two distinct colors when per-pierce coloring applied
    assert len(unique_colors) >= 2
