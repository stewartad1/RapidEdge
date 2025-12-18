from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest
pytest.importorskip("matplotlib", reason="Rendering requires matplotlib; install rendering extras to run.")

from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
from app.services import _annotate_bbox
from matplotlib.colors import to_rgba


def test_annotate_bbox_adds_rectangle_and_recolors_lines():
    fig = Figure()
    ax = fig.add_subplot(1, 1, 1)
    # draw a black line to simulate an object
    line, = ax.plot([0, 1], [0, 0], color="k")

    extmin = (0.0, 0.0, 0.0)
    extmax = (3.21, 2.78, 0.0)

    _annotate_bbox(ax, extmin, extmax, object_color="green", bbox_color="blue")

    # There should be at least one patch (the rectangular bbox)
    assert len(ax.patches) >= 1

    # Line color should be green now
    assert to_rgba(line.get_color()) == to_rgba("green")

    # bbox patch edge color should be blue
    rect = ax.patches[-1]
    assert to_rgba(rect.get_edgecolor()) == to_rgba("blue")


def test_render_png_respects_draw_bbox_flag(monkeypatch, tmp_path):
    """When DRAW_BBOX is False, render_dxf_png should not call the annotator.

    We monkeypatch the annotator to raise if called, set DRAW_BBOX False,
    and ensure render_dxf_png returns an image without triggering the annotator.
    """
    from app import services
    from app.services import render_dxf_png

    # create a simple DXF file
    import ezdxf
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    msp.add_line((0, 0), (10, 0))

    tmp = tmp_path / "tmp.dxf"
    doc.saveas(str(tmp))

    # Replace annotator with a function that raises if called
    def _fail(*args, **kwargs):
        raise AssertionError("_annotate_bbox should not be called when DRAW_BBOX is False")

    monkeypatch.setattr(services, "_annotate_bbox", _fail)

    # Turn off drawing
    monkeypatch.setattr(services, "DRAW_BBOX", False)

    # Should return PNG bytes without raising
    png = render_dxf_png(str(tmp))
    assert isinstance(png, (bytes, bytearray))


def test_render_png_calls_annotator_when_enabled(monkeypatch, tmp_path):
    """When DRAW_BBOX is True, render_dxf_png should call the annotator."""
    from app import services
    from app.services import render_dxf_png

    import ezdxf
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    msp.add_line((0, 0), (10, 0))

    tmp = tmp_path / "tmp2.dxf"
    doc.saveas(str(tmp))

    called = {"v": False}

    def _mark(*args, **kwargs):
        called["v"] = True

    monkeypatch.setattr(services, "_annotate_bbox", _mark)
    monkeypatch.setattr(services, "DRAW_BBOX", True)

    png = render_dxf_png(str(tmp))
    assert isinstance(png, (bytes, bytearray))
    assert called["v"] is True


def test_color_each_pierce_toggle_renders_multiple_colors(monkeypatch, tmp_path):
    """When COLOR_EACH_PIERCE is enabled, render_dxf_png should apply multiple colors to the rendered image."""
    from app import services
    from app.services import render_dxf_png

    # create a DXF with two lines (two pierces)
    import ezdxf
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    msp.add_line((0, 0), (10, 0))
    msp.add_line((0, 1), (10, 1))

    tmp = tmp_path / "tmp_pierces.dxf"
    doc.saveas(str(tmp))

    # Enable per-pierce coloring
    monkeypatch.setattr(services, "COLOR_EACH_PIERCE", True)
    monkeypatch.setattr(services, "PIERCE_COLORS", [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0)])

    # Render and ensure image produced
    img = render_dxf_png(str(tmp))
    assert isinstance(img, (bytes, bytearray, bytes)) or hasattr(img, "convert")

    # Convert to image if bytes
    from PIL import Image
    if isinstance(img, (bytes, bytearray)):
        from io import BytesIO
        img = Image.open(BytesIO(img))

    pixels = img.convert("RGBA").getdata()
    unique_colors = { (r,g,b) for (r,g,b,a) in pixels if a > 0 }
    # Expect at least two distinct colors when per-pierce coloring applied
    assert len(unique_colors) >= 2


def test_color_each_pierce_handles_collections():
    """Collections with multiple segments should receive per-segment colors."""
    from matplotlib.figure import Figure
    from matplotlib.collections import LineCollection
    from app.services import _color_each_pierce

    fig = Figure()
    ax = fig.add_subplot(1, 1, 1)

    segments = [ [(0, 0), (1, 0)], [(0, 1), (1, 1)], [(0,2),(1,2)] ]
    coll = LineCollection(segments, colors=[(0,0,0)])
    ax.add_collection(coll)

    # Use a 2-color palette to force cycling
    _color_each_pierce(ax, palette=["#ff0000", "#00ff00"])

    # The collection should now have multiple colors (one per segment)
    colors = coll.get_colors()
    assert len(colors) >= 2
    assert len({tuple(c) for c in colors}) >= 2


def test_color_each_pierce_splits_line2d_into_segments():
    """A single Line2D with NaN gaps should be split and colored per segment."""
    from matplotlib.figure import Figure
    from app.services import _color_each_pierce
    import numpy as np

    fig = Figure()
    ax = fig.add_subplot(1, 1, 1)

    x = [0, 1, np.nan, 2, 3, np.nan, 4, 5]
    y = [0, 0, np.nan, 1, 1, np.nan, 2, 2]
    # create a single artist with NaN-separated segments
    ax.plot(x, y, color='k')

    # Apply coloring with two colors
    _color_each_pierce(ax, palette=["#ff0000", "#00ff00"])

    # After splitting and coloring, expect at least 3 Line2D artists
    lines = ax.get_lines()
    assert len(lines) >= 3

    # Colors should vary among the lines
    colors = [l.get_color() for l in lines]
    assert len({c for c in colors if c is not None}) >= 2


def test_color_each_pierce_splits_line2d_on_large_gaps():
    """A Line2D with a large spatial gap should get split into multiple segments."""
    from matplotlib.figure import Figure
    from app.services import _color_each_pierce

    fig = Figure()
    ax = fig.add_subplot(1, 1, 1)

    # Create points with a large gap between (1,0) and (100,100)
    x = [0, 1, 100, 101]
    y = [0, 0, 100, 100]
    ax.plot(x, y, color='k')

    _color_each_pierce(ax, palette=["#ff0000", "#00ff00"])

    lines = ax.get_lines()
    # Expect split into at least two segments due to the large gap
    assert len(lines) >= 2

    colors = [l.get_color() for l in lines]
    assert len({c for c in colors if c is not None}) >= 2


def test_color_each_pierce_sets_linewidths():
    """When coloring is applied, line artists should have an increased linewidth."""
    from matplotlib.figure import Figure
    from app.services import _color_each_pierce

    fig = Figure()
    ax = fig.add_subplot(1, 1, 1)

    ax.plot([0, 1], [0, 0], linewidth=0.8)
    _color_each_pierce(ax, palette=["#ff0000", "#00ff00"])

    lines = ax.get_lines()
    assert any(getattr(l, 'get_linewidth', lambda: 0)() >= 1.5 for l in lines)
