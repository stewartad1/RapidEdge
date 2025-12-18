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
