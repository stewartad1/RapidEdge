import io
import os
import tempfile
from typing import TYPE_CHECKING, List, Optional

from fastapi import UploadFile

import ezdxf
from ezdxf.entities import DXFGraphic
from ezdxf.lldxf.const import DXFError

from .models import (
    Bounds,
    DxfDimensions,
    DxfEntity,
    DxfLayer,
    DxfMetadata,
    DxfParseResponse,
)

# Toggle drawing of axis-aligned bounding box in rendered PNGs.
# Set to False to disable bbox drawing (one-line change).
DRAW_BBOX = True

# Toggle per-pierce coloring: when True, each unbroken entity (LINE, CIRCLE,
# ARC, POLYLINE) will be drawn with a different color. Set to False to disable.
# This is intentionally a single-line code toggle; change it here and restart the
# server to enable/disable per-pierce coloring. Default: False
COLOR_EACH_PIERCE = False

# Default palette to cycle when coloring individual pierces.
# Use a bright/high-contrast palette so per-pierce colors are visible on dark backgrounds.
PIERCE_COLORS = [
    "#ff0000",  # red
    "#00ff00",  # lime
    "#0000ff",  # blue
    "#ffff00",  # yellow
    "#ff00ff",  # magenta
    "#00ffff",  # cyan
    "#ff7f0e",  # orange
    "#9467bd",  # purple
    "#8c564b",  # brown
    "#ffffff",  # white
]


def _round_to(value: float, ndigits: int = 3) -> float:
    """Round to at most `ndigits` decimal places for presentation stability.

    Placing this helper at module level lets us apply consistent rounding to any
    DXF-derived numeric output (bounds, measurements, areas, etc.).
    """
    return round(float(value), ndigits)

if TYPE_CHECKING:  # pragma: no cover - import-time guard for optional deps
    from ezdxf.addons.drawing import Frontend, RenderContext
    from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
    from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
    from matplotlib.figure import Figure


def _compute_entity_bounds(entities: List[DXFGraphic]) -> Optional[Bounds]:
    """Calculate bounds using ezdxf's bounding box helper.

    ezdxf's :class:`~ezdxf.math.BoundingBox` aggregates extents across all
    entities and supports the full DXF entity set, so we rely on it to keep
    measurements aligned with the library's own geometry routines.

    The coordinates are rounded to at most three decimal places to avoid
    exposing floating-point representation noise to API consumers.
    """

    from ezdxf import bbox as ez_bbox

    try:
        bbox = ez_bbox.extents(entities)
    except ez_bbox.BoundingBoxError:
        return None

    return Bounds(
        min_x=_round_to(bbox.extmin[0]),
        min_y=_round_to(bbox.extmin[1]),
        min_z=_round_to(bbox.extmin[2]),
        max_x=_round_to(bbox.extmax[0]),
        max_y=_round_to(bbox.extmax[1]),
        max_z=_round_to(bbox.extmax[2]),
    )


def _extract_layers(doc) -> List[DxfLayer]:
    return [
        DxfLayer(name=layer.dxf.name, color=layer.color)
        for layer in doc.layers
    ]


def _extract_entities(msp) -> List[DXFGraphic]:
    return list(msp)


def _count_unbroken_entities(entities):
    """Return counts of unbroken line-like entities.

    Returns a tuple: (lines, circles, arcs, polylines, total_pierces)
    where total_pierces counts each LINE/CIRCLE/ARC/POLYLINE as one unbroken
    entity (i.e., one pierce per entity).
    """
    lines = 0
    circles = 0
    arcs = 0
    polylines = 0

    for e in entities:
        et = e.dxftype()
        if et == "LINE":
            lines += 1
        elif et == "CIRCLE":
            circles += 1
        elif et == "ARC":
            arcs += 1
        elif et in {"LWPOLYLINE", "POLYLINE"}:
            polylines += 1

    total = lines + circles + arcs + polylines
    return lines, circles, arcs, polylines, total


def parse_dxf(file_path: str, filename: str) -> DxfParseResponse:
    try:
        # ezdxf reads directly from a filesystem path and handles both ASCII and
        # binary DXF files transparently.
        doc = ezdxf.readfile(file_path)
    except (DXFError, IOError) as exc:  # DXFError for invalid files
        raise ValueError(f"Invalid DXF file: {exc}") from exc

    msp = doc.modelspace()
    metadata = DxfMetadata(
        filename=filename,
        version=doc.acad_release,
        units=doc.header.get("$INSUNITS"),
    )

    layers = _extract_layers(doc)
    entity_objs = _extract_entities(msp)
    entities = [DxfEntity(type=e.dxftype(), layer=e.dxf.layer) for e in entity_objs]
    bounds = _compute_entity_bounds(entity_objs)

    lines, circles, arcs, polylines, total = _count_unbroken_entities(entity_objs)

    return DxfParseResponse(
        metadata=metadata,
        layers=layers,
        entities=entities,
        bounds=bounds,
        number_of_lines=lines,
        number_of_circles=circles,
        number_of_arcs=arcs,
        number_of_polylines=polylines,
        number_of_pierces=total,
    )


def measure_dxf(file_path: str) -> DxfDimensions:
    """Calculate maximum width/length in both millimeters and inches."""

    from ezdxf import bbox as ez_bbox
    from ezdxf import units as ez_units

    try:
        doc = ezdxf.readfile(file_path)
    except (DXFError, IOError) as exc:
        raise ValueError(f"Invalid DXF file: {exc}") from exc

    msp = doc.modelspace()
    try:
        bbox = ez_bbox.extents(msp)
    except ez_bbox.BoundingBoxError as exc:
        raise ValueError("DXF has no measurable entities.") from exc

    # Use axis-aligned bounding box extents. To keep `width` reporting
    # consistent regardless of drawing orientation, define `width` as the
    # larger of the X/Y extents and `length` as the smaller. This avoids
    # accidentally reporting the triangle's height when the drawing is rotated.
    x_extent = float(bbox.extmax[0] - bbox.extmin[0])
    y_extent = float(bbox.extmax[1] - bbox.extmin[1])
    # Define object dimensions (existing behavior) as the larger and smaller
    # of the X/Y extents respectively. These are renamed to be explicit.
    object_width = max(x_extent, y_extent)
    object_length = min(x_extent, y_extent)

    raw_units = int(doc.header.get("$INSUNITS", 0) or 0)
    base_unit_value = raw_units if raw_units > 0 else ez_units.MM

    def _convert(value: float, target: int) -> float:
        factor = ez_units.conversion_factor(base_unit_value, target)
        return _round_to(value * factor)

    # Object dimensions
    object_width_mm = _convert(object_width, ez_units.MM)
    object_length_mm = _convert(object_length, ez_units.MM)
    object_width_in = _convert(object_width, ez_units.IN)
    object_length_in = _convert(object_length, ez_units.IN)

    # Bounding-box (axis-aligned) dimensions: use raw x/y extents
    bbox_width_mm = _convert(x_extent, ez_units.MM)
    bbox_length_mm = _convert(y_extent, ez_units.MM)
    bbox_width_in = _convert(x_extent, ez_units.IN)
    bbox_length_in = _convert(y_extent, ez_units.IN)

    # Area should represent the bounding-box area
    square_inches = _round_to(bbox_width_in * bbox_length_in)

    # Compute maximum edge length by scanning segment-like entities.
    # We collect endpoints from LINE and polyline entities and compute the
    # maximum distance between any two points (this captures the longest
    # straight segment present in the drawing, which is a practical definition
    # of "max edge length" for our purposes).
    points = []
    for entity in msp:
        et = entity.dxftype()
        if et == "LINE":
            # LINE exposes start/end as 3-tuples
            points.append(tuple(entity.dxf.start))
            points.append(tuple(entity.dxf.end))
        elif et in {"LWPOLYLINE", "POLYLINE"}:
            # LWPOLYLINE supports get_points(); POLYLINE may provide vertices()
            try:
                pts = list(entity.get_points())
                for p in pts:
                    points.append((p[0], p[1], p[2] if len(p) > 2 else 0.0))
            except Exception:
                # POLYLINE fallback: try vertices (some versions expose .vertices())
                try:
                    for v in entity.vertices():
                        points.append((v.dxf.x, v.dxf.y, getattr(v.dxf, "z", 0.0)))
                except Exception:
                    # Best-effort: skip if we can't iterate points
                    continue

    max_edge = 0.0
    pts2 = []  # 2D points for OBB/hull
    if len(points) >= 2:
        import math

        # build 2D points list and compute max pairwise distance (O(n^2))
        n = len(points)
        for i in range(n):
            x1, y1, z1 = points[i]
            pts2.append((float(x1), float(y1)))
            for j in range(i + 1, n):
                x2, y2, z2 = points[j]
                dx = x2 - x1
                dy = y2 - y1
                dz = z2 - z1
                d = math.hypot(math.hypot(dx, dy), dz)
                if d > max_edge:
                    max_edge = d

    max_edge_mm = _convert(max_edge, ez_units.MM)
    max_edge_in = _convert(max_edge, ez_units.IN)

    # Oriented Bounding Box (minimum-area rectangle) via convex hull rotating calipers.
    def _convex_hull(points_2d):
        # Monotone chain convex hull (returns list in CCW order)
        pts = sorted(set(points_2d))
        if len(pts) <= 1:
            return pts

        def cross(o, a, b):
            return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

        lower = []
        for p in pts:
            while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
                lower.pop()
            lower.append(p)

        upper = []
        for p in reversed(pts):
            while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
                upper.pop()
            upper.append(p)

        # Concatenate lower and upper to get full hull (last point of each is omitted)
        return lower[:-1] + upper[:-1]

    def _min_area_rect(hull_pts):
        import math

        if len(hull_pts) == 0:
            return 0.0, 0.0, 0.0
        if len(hull_pts) == 1:
            return 0.0, 0.0, 0.0
        if len(hull_pts) == 2:
            # Rectangle degenerates to segment length and zero width
            dx = hull_pts[1][0] - hull_pts[0][0]
            dy = hull_pts[1][1] - hull_pts[0][1]
            length = math.hypot(dx, dy)
            return length, 0.0, math.degrees(math.atan2(dy, dx))

        best_area = float("inf")
        best_w = 0.0
        best_h = 0.0
        best_angle = 0.0

        for i in range(len(hull_pts)):
            p1 = hull_pts[i]
            p2 = hull_pts[(i + 1) % len(hull_pts)]
            edge_dx = p2[0] - p1[0]
            edge_dy = p2[1] - p1[1]
            angle = math.atan2(edge_dy, edge_dx)
            cos_a = math.cos(-angle)
            sin_a = math.sin(-angle)

            xs = []
            ys = []
            for (x, y) in hull_pts:
                rx = x * cos_a - y * sin_a
                ry = x * sin_a + y * cos_a
                xs.append(rx)
                ys.append(ry)

            min_x = min(xs)
            max_x = max(xs)
            min_y = min(ys)
            max_y = max(ys)

            w = max_x - min_x
            h = max_y - min_y
            area = w * h
            if area < best_area:
                best_area = area
                # define width as the longer side for consistent naming
                if w >= h:
                    best_w = w
                    best_h = h
                else:
                    best_w = h
                    best_h = w
                # store angle in degrees CCW relative to X axis
                best_angle = math.degrees(angle)

        return best_w, best_h, best_angle

    obb_w = 0.0
    obb_h = 0.0
    obb_angle = 0.0
    min_max_w = 0.0
    min_max_h = 0.0
    min_max_angle = 0.0
    min_max_metric = float("inf")
    min_max_area = float("inf")

    min_square_side = 0.0

    if pts2:
        hull = _convex_hull(pts2)

        # First compute OBB (min-area rectangle)
        obb_w, obb_h, obb_angle = _min_area_rect(hull)

        # Evaluate candidate rectangles for each hull edge angle to find the
        # rectangle that minimizes the maximum side (minimize max(width, height)).
        for i in range(len(hull)):
            p1 = hull[i]
            p2 = hull[(i + 1) % len(hull)]
            edge_dx = p2[0] - p1[0]
            edge_dy = p2[1] - p1[1]
            angle = math.atan2(edge_dy, edge_dx)
            cos_a = math.cos(-angle)
            sin_a = math.sin(-angle)

            xs = []
            ys = []
            for (x, y) in hull:
                rx = x * cos_a - y * sin_a
                ry = x * sin_a + y * cos_a
                xs.append(rx)
                ys.append(ry)

            min_x = min(xs)
            max_x = max(xs)
            min_y = min(ys)
            max_y = max(ys)

            w = max_x - min_x
            h = max_y - min_y
            area = w * h
            metric = max(w, h)  # max-side metric

            # Choose candidate that minimizes the maximum side (minimize metric)
            # tie-breaker: choose smaller area
            if metric < min_max_metric or (metric == min_max_metric and area < min_max_area):
                min_max_metric = metric
                min_max_w = w if w >= h else h
                min_max_h = h if w >= h else w
                min_max_angle = math.degrees(angle)
                min_max_area = area

        # minimal enclosing square side is the minimum possible max side
        min_square_side = min_max_metric

    # Prepare conversions and rounding
    obb_width_mm = _convert(obb_w, ez_units.MM)
    obb_length_mm = _convert(obb_h, ez_units.MM)
    obb_width_in = _convert(obb_w, ez_units.IN)
    obb_length_in = _convert(obb_h, ez_units.IN)

    min_max_rect_width_mm = _convert(min_max_w, ez_units.MM)
    min_max_rect_length_mm = _convert(min_max_h, ez_units.MM)
    min_max_rect_width_in = _convert(min_max_w, ez_units.IN)
    min_max_rect_length_in = _convert(min_max_h, ez_units.IN)
    min_max_rect_angle = _round_to(min_max_angle)

    min_enclosing_square_side_mm = _convert(min_square_side, ez_units.MM)
    min_enclosing_square_side_in = _convert(min_square_side, ez_units.IN)

    unit_label = ez_units.unit_name(base_unit_value)

    return DxfDimensions(
        object_width_mm=object_width_mm,
        object_width_in=object_width_in,
        object_length_mm=object_length_mm,
        object_length_in=object_length_in,
        bbox_width_mm=bbox_width_mm,
        bbox_width_in=bbox_width_in,
        bbox_length_mm=bbox_length_mm,
        bbox_length_in=bbox_length_in,
        square_inches=square_inches,
        max_edge_length_mm=max_edge_mm,
        max_edge_length_in=max_edge_in,
        obb_width_mm=obb_width_mm,
        obb_width_in=obb_width_in,
        obb_length_mm=obb_length_mm,
        obb_length_in=obb_length_in,
        obb_angle_deg=_round_to(obb_angle, 3),
        min_max_rect_width_mm=min_max_rect_width_mm,
        min_max_rect_width_in=min_max_rect_width_in,
        min_max_rect_length_mm=min_max_rect_length_mm,
        min_max_rect_length_in=min_max_rect_length_in,
        min_max_rect_angle_deg=min_max_rect_angle,
        min_enclosing_square_side_mm=min_enclosing_square_side_mm,
        min_enclosing_square_side_in=min_enclosing_square_side_in,
        source_units=unit_label,
    )


def _annotate_bbox(ax, extmin, extmax, object_color: str = "green", bbox_color: str = "blue"):
    """Annotate an existing Matplotlib axes with colored object lines and
    a bounding box rectangle.

    - Optionally recolors existing line artists and collections to `object_color`.
      If `object_color` is None, recoloring is skipped (useful when per-pierce
      coloring is applied separately).
    - Adds an axis-aligned rectangle from `extmin` to `extmax` in `bbox_color`.
    """
    try:
        import matplotlib
        from matplotlib.patches import Rectangle
        from matplotlib.colors import to_rgba
    except Exception:  # pragma: no cover - defensive
        return

    # Recolor lines only when an object_color is provided
    if object_color:
        for line in ax.get_lines():
            line.set_color(object_color)
        # Recolor collections if present (line/polyline renderings may produce collections)
        for col in getattr(ax, "collections", []):
            try:
                col.set_color(object_color)
            except Exception:
                try:
                    col.set_edgecolor(object_color)
                except Exception:
                    pass

    # Add bounding box rectangle
    min_x = float(extmin[0])
    min_y = float(extmin[1])
    width = float(extmax[0] - extmin[0])
    height = float(extmax[1] - extmin[1])

    rect = Rectangle((min_x, min_y), width, height, fill=False, edgecolor=bbox_color, linewidth=1.5, zorder=10)
    ax.add_patch(rect)


def _color_each_pierce(ax, palette=None):
    """Color each visible pierce (Line2D and collections) using `palette`.

    The function cycles through the provided palette and assigns colors to
    line artists and collections found on the axes. It handles Line2D and
    different collection types (e.g., LineCollection / PathCollection). For
    collections that contain multiple sub-paths, it assigns a distinct color
    to each sub-path so per-pierce coloring is visible even when a backend
    groups segments into a single collection.
    """
    if palette is None:
        palette = PIERCE_COLORS

    from matplotlib.colors import to_rgba
    from matplotlib.lines import Line2D
    from matplotlib.collections import LineCollection

    artists = []
    # prefer explicit lines first
    artists.extend(ax.get_lines())
    # then path/line collections (e.g., polylines)
    artists.extend(getattr(ax, "collections", []))

    color_index = 0

    # Before coloring, split Line2D artists into separate artists for
    # disjoint sub-segments so we can color each pierce independently.
    new_lines = []
    for line in list(ax.get_lines()):
        try:
            x = line.get_xdata()
            y = line.get_ydata()
        except Exception:
            continue
        if len(x) < 2:
            continue

        import numpy as np

        xa = np.asarray(x, dtype=float)
        ya = np.asarray(y, dtype=float)

        # Break at explicit NaNs
        nan_mask = np.isnan(xa) | np.isnan(ya)
        if nan_mask.any():
            # Split into contiguous non-NaN ranges
            indices = np.where(~nan_mask)[0]
            if len(indices) == 0:
                continue
            # group consecutive indices
            groups = np.split(indices, np.where(np.diff(indices) != 1)[0] + 1)
        else:
            # No NaNs: detect large jumps between consecutive points and split
            dx = np.diff(xa)
            dy = np.diff(ya)
            d = np.hypot(dx, dy)
            # threshold relative to drawing size
            x0, x1 = ax.get_xlim()
            y0, y1 = ax.get_ylim()
            diag = max(1e-6, ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5)
            # Use 1% of diagonal as gap threshold
            threshold = diag * 0.01
            split_idx = np.where(d > threshold)[0]
            if len(split_idx) == 0:
                groups = [np.arange(len(xa))]
            else:
                cuts = (split_idx + 1).tolist()
                groups = np.split(np.arange(len(xa)), cuts)

        # If we have more than one group, replace the original Line2D with
        # separate Line2D artists, preserving line style where possible.
        if len(groups) > 1:
            try:
                ax.lines.remove(line)
            except Exception:
                try:
                    ax.get_lines().remove(line)
                except Exception:
                    pass

            for g in groups:
                if len(g) < 2:
                    continue
                xs = xa[g]
                ys = ya[g]
                new_line = Line2D(xs, ys,
                                  linewidth=line.get_linewidth(),
                                  linestyle=line.get_linestyle(),
                                  solid_capstyle=line.get_solid_capstyle(),
                                  zorder=line.get_zorder())
                ax.add_line(new_line)
                new_lines.append(new_line)

    # If we replaced lines, refresh the list used for coloring
    if new_lines:
        artists = []
        artists.extend(ax.get_lines())
        artists.extend(getattr(ax, "collections", []))

    for art in artists:
        # Handle simple Line2D artists (one color per artist)
        if isinstance(art, Line2D):
            color = palette[color_index % len(palette)]
            try:
                art.set_color(color)
                # increase linewidth so the color is more visible on dark backgrounds
                try:
                    lw = float(art.get_linewidth() or 0) or 0
                    if lw < 1.5:
                        art.set_linewidth(1.5)
                except Exception:
                    pass
            except Exception:
                pass
            color_index += 1
            continue

        # Collections: try to determine number of sub-elements
        n_sub = 1
        try:
            # LineCollection exposes segments via .get_segments()
            if isinstance(art, LineCollection):
                n_sub = len(art.get_segments())
            else:
                # Generic collections may expose multiple paths
                paths = art.get_paths()
                n_sub = len(paths) if paths is not None else 1
        except Exception:
            n_sub = 1

        if n_sub <= 1:
            # Single-element collection: color as a single artist
            color = palette[color_index % len(palette)]
            try:
                art.set_color(color)
            except Exception:
                try:
                    art.set_edgecolor(color)
                except Exception:
                    try:
                        art.set_facecolor(color)
                    except Exception:
                        pass
            color_index += 1
        else:
            # Multi-element collection: assign per-sub-element colors
            colors = [to_rgba(palette[(color_index + j) % len(palette)]) for j in range(n_sub)]
            try:
                # Prefer edgecolors for line-like collections
                art.set_edgecolors(colors)
                try:
                    # make sure the linewidths are visible
                    if hasattr(art, 'set_linewidths'):
                        art.set_linewidths([1.5] * n_sub)
                    elif hasattr(art, 'set_linewidth'):
                        art.set_linewidth(1.5)
                except Exception:
                    pass
            except Exception:
                try:
                    art.set_facecolors(colors)
                except Exception:
                    try:
                        art.set_color(colors)
                    except Exception:
                        pass
            color_index += n_sub


def render_dxf_png(file_path: str) -> bytes:
    """Render a DXF file to a PNG image using ezdxf's drawing addon.

    The function keeps rendering deterministic and headless-friendly by using
    Matplotlib's Agg backend and equal aspect ratio. It raises ``ValueError`` if
    ezdxf cannot read the file.
    """

    try:
        from ezdxf.addons.drawing import Frontend, RenderContext
        from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
        import matplotlib

        matplotlib.use("Agg")
        from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
        from matplotlib.figure import Figure
    except ImportError as exc:  # pragma: no cover - exercised in integration
        raise ValueError(
            "Rendering dependencies missing; install matplotlib and Pillow."
        ) from exc

    try:
        doc = ezdxf.readfile(file_path)
    except (DXFError, IOError) as exc:
        raise ValueError(f"Invalid DXF file: {exc}") from exc

    msp = doc.modelspace()

    fig = Figure()
    ax = fig.add_subplot(1, 1, 1)
    ax.set_aspect("equal")

    ctx = RenderContext(doc)
    backend = MatplotlibBackend(ax)
    Frontend(ctx, backend).draw_layout(msp, finalize=True)

    # Draw axis-aligned bounding box and recolor objects (or color each pierce)
    try:
        from ezdxf import bbox as ez_bbox
        bbox = ez_bbox.extents(msp)

        # If per-pierce coloring is enabled, skip global recolor and color each
        # pierce individually after drawing. Otherwise, recolor objects green.
        if DRAW_BBOX:
            obj_color = None if COLOR_EACH_PIERCE else "green"
            _annotate_bbox(ax, bbox.extmin, bbox.extmax, object_color=obj_color, bbox_color="blue")

        if COLOR_EACH_PIERCE:
            _color_each_pierce(ax)
    except Exception:
        # If bbox computation or annotation fails, continue to return the image
        pass

    canvas = FigureCanvas(fig)
    buffer = io.BytesIO()
    canvas.print_png(buffer)
    return buffer.getvalue()


async def save_upload_to_temp(upload: UploadFile) -> str:
    """Persist an ``UploadFile`` to a temporary file and return the path.

    Reading the upload contents explicitly ensures we capture the file data even
    when the underlying stream has been consumed or is waiting to be read (as
    can happen with the Swagger "Try it out" flow). The bytes are then written
    to a temporary DXF file path for ezdxf to consume.
    """
    await upload.seek(0)
    contents = await upload.read()
    if not contents:
        raise ValueError("Uploaded file is empty.")
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".dxf")
    try:
        tmp.write(contents)
        tmp.flush()
        return tmp.name
    finally:
        tmp.close()


def remove_file_safely(path: str) -> None:
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


def inspect_dxf(file_path: str, join_tol: float = 0.0, unit: str = "millimeters") -> dict:
    """Return a JSON-serializable inspection of entities in the DXF file.

    The returned dict includes per-entity diagnostics (type, layer, bbox,
    vertex count, and a simple summary) and aggregated counts by type. Use
    this to diagnose mismatches between parsed counts and rendering behavior.
    """
    try:
        doc = ezdxf.readfile(file_path)
    except (DXFError, IOError) as exc:
        raise ValueError(f"Invalid DXF file: {exc}") from exc

    msp = doc.modelspace()
    entities = list(msp)

    counts = {"LINE": 0, "CIRCLE": 0, "ARC": 0, "LWPOLYLINE": 0, "POLYLINE": 0}
    items = []

    from ezdxf import bbox as ez_bbox


    total_line_length = 0.0

    # Unit conversion factors (from drawing units to output units)
    # Supported: "millimeters", "inches", "centimeters", "meters"
    def _unit_factor(doc, target_unit: str):
        # Try to get INSUNITS from DXF header
        insunits = None
        try:
            insunits = int(doc.header.get("$INSUNITS", 0))
        except Exception:
            pass
        # ezdxf INSUNITS codes: 1=inch, 4=mm, 2=feet, 5=cm, 6=m, 0=unitless
        # Default to mm if not set
        code_to_mm = {1: 25.4, 4: 1.0, 2: 304.8, 5: 10.0, 6: 1000.0, 0: 1.0}
        mm_per_drawing = code_to_mm.get(insunits, 1.0)
        if target_unit == "millimeters":
            return mm_per_drawing
        elif target_unit == "inches":
            return mm_per_drawing / 25.4
        elif target_unit == "centimeters":
            return mm_per_drawing / 10.0
        elif target_unit == "meters":
            return mm_per_drawing / 1000.0
        else:
            return 1.0  # fallback: no conversion

    # Read doc for units
    try:
        doc = ezdxf.readfile(file_path)
    except (DXFError, IOError) as exc:
        raise ValueError(f"Invalid DXF file: {exc}") from exc
    factor = _unit_factor(doc, unit)
    msp = doc.modelspace()
    entities = list(msp)
    for idx, ent in enumerate(entities):
        et = ent.dxftype()
        if et in counts:
            counts[et] += 1
        # compute bbox for single entity
        try:
            bb = ez_bbox.extents([ent])
            bbox = {
                "min_x": _round_to(bb.extmin[0]),
                "min_y": _round_to(bb.extmin[1]),
                "max_x": _round_to(bb.extmax[0]),
                "max_y": _round_to(bb.extmax[1]),
            }
        except Exception:
            bbox = None

        # vertex / point counts depending on type
        vcount = None
        summary = None
        length = None
        try:
            import math
            if et == "LINE":
                start = tuple(map(float, ent.dxf.start))
                end = tuple(map(float, ent.dxf.end))
                vcount = 2
                summary = {"start": [start[0], start[1]], "end": [end[0], end[1]]}
                length = math.hypot(end[0] - start[0], end[1] - start[1])
            elif et == "CIRCLE":
                center = tuple(map(float, ent.dxf.center))
                r = float(ent.dxf.radius)
                vcount = 1
                summary = {"center": [center[0], center[1]], "radius": r}
                length = 2 * math.pi * r
            elif et == "ARC":
                center = tuple(map(float, ent.dxf.center))
                r = float(ent.dxf.radius)
                vcount = 1
                summary = {"center": [center[0], center[1]], "radius": r}
                sa = float(getattr(ent.dxf, "start_angle", getattr(ent, "start_angle", 0)))
                ea = float(getattr(ent.dxf, "end_angle", getattr(ent, "end_angle", 0)))
                # Arc length = r * angle (in radians)
                angle = (ea - sa) % 360
                length = math.radians(angle) * r
            elif et in {"LWPOLYLINE", "POLYLINE"}:
                try:
                    pts = list(ent.get_points())
                except Exception:
                    # fallback for older APIs
                    pts = list(ent.vertices())
                vcount = len(pts)
                summary = {"points": [[float(x), float(y)] for x, y, *_ in pts]}
                length = 0.0
                prev = None
                first = None
                for pt in pts:
                    x, y = float(pt[0]), float(pt[1])
                    if prev is not None:
                        length += math.hypot(x - prev[0], y - prev[1])
                    else:
                        first = (x, y)
                    prev = (x, y)
                # If closed, add segment from last to first
                is_closed = False
                try:
                    is_closed = bool(getattr(ent, 'closed', False)) or (hasattr(ent.dxf, 'flags') and (ent.dxf.flags & 1))
                except Exception:
                    pass
                if is_closed and first and prev and prev != first:
                    length += math.hypot(first[0] - prev[0], first[1] - prev[1])
            elif et == "SPLINE":
                # Approximate length by tessellating the spline into line segments
                points = []
                try:
                    points = ent.approximate(segments=100)
                    points = [(float(pt[0]), float(pt[1])) for pt in points]
                except Exception:
                    pass
                if not points:
                    # fallback: use control points if available
                    try:
                        ctrl = ent.control_points
                        points = [(float(pt[0]), float(pt[1])) for pt in ctrl]
                    except Exception:
                        points = []
                vcount = len(points)
                summary = {"points": [[x, y] for x, y in points]}
                length = 0.0
                prev = None
                for pt in points:
                    x, y = pt
                    if prev is not None:
                        length += math.hypot(x - prev[0], y - prev[1])
                    prev = (x, y)
                # If still zero, try to estimate by control polygon length
                if length == 0.0 and len(points) > 1:
                    for i in range(1, len(points)):
                        length += math.hypot(points[i][0] - points[i-1][0], points[i][1] - points[i-1][1])
            elif et == "ELLIPSE":
                # Approximate ellipse arc length using parametric sampling
                points = []
                try:
                    import numpy as np
                    start_param = float(getattr(ent.dxf, "start_param", 0.0))
                    end_param = float(getattr(ent.dxf, "end_param", 2 * math.pi))
                    ratio = float(ent.dxf.radius_ratio)
                    major = float(ent.dxf.major_axis.magnitude)
                    center = tuple(map(float, ent.dxf.center))
                    num = 100
                    ts = np.linspace(start_param, end_param, num=num)
                    points = [(
                        center[0] + major * np.cos(t),
                        center[1] + major * ratio * np.sin(t)
                    ) for t in ts]
                except Exception:
                    pass
                vcount = len(points)
                summary = {"points": [[x, y] for x, y in points]}
                length = 0.0
                prev = None
                for pt in points:
                    x, y = pt
                    if prev is not None:
                        length += math.hypot(x - prev[0], y - prev[1])
                    prev = (x, y)
                # If still zero, estimate full ellipse circumference if possible
                if length == 0.0:
                    try:
                        import math
                        a = float(ent.dxf.major_axis.magnitude)
                        b = a * float(ent.dxf.radius_ratio)
                        # Ramanujan's approximation for ellipse circumference
                        h = ((a-b)**2)/((a+b)**2) if (a+b) != 0 else 0
                        circ = math.pi * (a + b) * (1 + (3*h)/(10 + math.sqrt(4-3*h)))
                        length = circ
                    except Exception:
                        length = 0.0
            elif et == "ELLIPSE":
                # Approximate ellipse arc length using parametric sampling
                try:
                    import numpy as np
                    start_param = float(getattr(ent.dxf, "start_param", 0.0))
                    end_param = float(getattr(ent.dxf, "end_param", 2 * math.pi))
                    ratio = float(ent.dxf.radius_ratio)
                    major = float(ent.dxf.major_axis.magnitude)
                    center = tuple(map(float, ent.dxf.center))
                    num = 100
                    ts = np.linspace(start_param, end_param, num=num)
                    points = [(
                        center[0] + major * np.cos(t),
                        center[1] + major * ratio * np.sin(t)
                    ) for t in ts]
                except Exception:
                    points = []
                vcount = len(points)
                summary = {"points": [[x, y] for x, y in points]}
                length = 0.0
                prev = None
                for pt in points:
                    x, y = pt
                    if prev is not None:
                        length += math.hypot(x - prev[0], y - prev[1])
                    prev = (x, y)
        except Exception:
            pass

        if length is not None:
            total_line_length += length

        items.append(
            {
                "index": idx,
                "type": et,
                "layer": getattr(ent.dxf, "layer", None),
                "bbox": bbox,
                "vertex_count": vcount,
                "summary": summary,
                "length": _round_to(length * factor) if length is not None else None,
            }
        )

    total_pierces = counts.get("LINE", 0) + counts.get("CIRCLE", 0) + counts.get("ARC", 0) + counts.get("LWPOLYLINE", 0) + counts.get("POLYLINE", 0)

    # Build connectivity graph based on shared endpoints (zero-gap connectivity)
    def _endpoints_for_entity(ent):
        et = ent.dxftype()
        pts = []
        try:
            if et == "LINE":
                s = ent.dxf.start
                e = ent.dxf.end
                pts = [(float(s[0]), float(s[1])), (float(e[0]), float(e[1]))]
            elif et == "ARC":
                cx, cy = float(ent.dxf.center[0]), float(ent.dxf.center[1])
                r = float(ent.dxf.radius)
                sa = float(getattr(ent.dxf, "start_angle", getattr(ent, "start_angle", 0)))
                ea = float(getattr(ent.dxf, "end_angle", getattr(ent, "end_angle", 0)))
                import math

                srad = math.radians(sa)
                erad = math.radians(ea)
                pts = [(cx + r * math.cos(srad), cy + r * math.sin(srad)), (cx + r * math.cos(erad), cy + r * math.sin(erad))]
            elif et == "CIRCLE":
                # circle has no endpoints but keep center/radius for on-circle checks
                pts = []
            elif et in {"LWPOLYLINE", "POLYLINE"}:
                try:
                    pts_raw = list(ent.get_points())
                except Exception:
                    pts_raw = []
                    try:
                        for v in ent.vertices():
                            pts_raw.append((v.dxf.location[0], v.dxf.location[1]))
                    except Exception:
                        pass
                pts = [(float(x), float(y)) for (x, y, *_) in pts_raw if not (x is None or y is None)]
        except Exception:
            pts = []
        return pts

    endpoints = [ _endpoints_for_entity(ent) for ent in entities ]

    # helper: quantize point to stable keys
    def _key(pt, ndigits=6):
        return (round(pt[0], ndigits), round(pt[1], ndigits))

    point_map: dict = {}
    for idx, pts in enumerate(endpoints):
        for p in pts:
            point_map.setdefault(_key(p), set()).add(idx)

    # Union-find for components
    parent = list(range(len(entities)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    # Connect entities that share a quantized point
    for idxs in point_map.values():
        idl = list(idxs)
        for i in range(1, len(idl)):
            union(idl[0], idl[i])

    # Also merge points that are very close within join_tol so small numeric
    # gaps don't create extra pierces. join_tol is passed into this function
    # and defaults to 0.0 (zero disconnect required).
    import math
    point_keys = list(point_map.keys())
    for i in range(len(point_keys)):
        x1, y1 = point_keys[i]
        for j in range(i + 1, len(point_keys)):
            x2, y2 = point_keys[j]
            if math.hypot(x1 - x2, y1 - y2) <= join_tol:
                # union all entities that reference these close points
                set_i = point_map.get(point_keys[i], set())
                set_j = point_map.get(point_keys[j], set())
                ids = list(set_i | set_j)
                for k in range(1, len(ids)):
                    union(ids[0], ids[k])

    # Additionally, connect entities that touch a circle: endpoint lies on circle (within tolerance)
    tol = join_tol
    circle_indices = [i for i, e in enumerate(entities) if e.dxftype() == "CIRCLE"]
    for ci in circle_indices:
        ent = entities[ci]
        cx, cy = float(ent.dxf.center[0]), float(ent.dxf.center[1])
        r = float(ent.dxf.radius)
        for j, pts in enumerate(endpoints):
            for p in pts:
                if abs(math.hypot(p[0]-cx, p[1]-cy) - r) <= tol:
                    union(ci, j)

    # Build components
    comps = {}
    for i in range(len(entities)):
        root = find(i)
        comps.setdefault(root, []).append(i)

    # Count components that include pierceable entity types
    pierce_types = {"LINE", "CIRCLE", "ARC", "LWPOLYLINE", "POLYLINE"}
    connected_components = []
    for comp in comps.values():
        if any(entities[i].dxftype() in pierce_types for i in comp):
            connected_components.append(comp)

    connected_pierces = len(connected_components)

    # Provide components with entity indices and combined bbox for ease of use
    comp_details = []
    for comp in connected_components:
        # combine bbox
        min_x = min((it["bbox"]["min_x"] for it in [items[i] for i in comp] if it["bbox"] is not None), default=None)
        min_y = min((it["bbox"]["min_y"] for it in [items[i] for i in comp] if it["bbox"] is not None), default=None)
        max_x = max((it["bbox"]["max_x"] for it in [items[i] for i in comp] if it["bbox"] is not None), default=None)
        max_y = max((it["bbox"]["max_y"] for it in [items[i] for i in comp] if it["bbox"] is not None), default=None)
        comp_details.append({"entities": comp, "bbox": {"min_x": min_x, "min_y": min_y, "max_x": max_x, "max_y": max_y}})

    return {
        "counts": counts,
        "number_of_pierces": total_pierces,
        "entities": items,
        "connected_pierces": connected_pierces,
        "components": comp_details,
        "total_line_length": _round_to(total_line_length * factor) if total_line_length is not None else None,
        "output_units": unit,
    }


from matplotlib.patches import Rectangle

def render_entity_bboxes(file_path: str) -> bytes:
    """Render an image that overlays a distinct-colored bbox for each entity.

    This debug rendering helps visually identify which entities are present and
    where they are located. The function cycles colors for each entity and
    writes the entity index near its bbox for easier cross-referencing.
    """
    try:
        import matplotlib

        matplotlib.use("Agg")
        from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
        from matplotlib.figure import Figure
    except Exception as exc:  # pragma: no cover - integration-only
        raise ValueError("Rendering dependencies missing; install matplotlib and Pillow.") from exc

    try:
        doc = ezdxf.readfile(file_path)
    except (DXFError, IOError) as exc:
        raise ValueError(f"Invalid DXF file: {exc}") from exc

    msp = doc.modelspace()
    # Use a larger figure and autoscale to the combined entity bboxes so the
    # labels and boxes are visible in Swagger UI.
    fig = Figure(figsize=(10, 8))
    ax = fig.add_subplot(1, 1, 1)
    ax.set_aspect("equal")

    try:
        from ezdxf import bbox as ez_bbox
    except Exception:
        ez_bbox = None

    entities = list(msp)

    all_mins = []
    all_maxs = []
    for i, ent in enumerate(entities):
        try:
            bb = ez_bbox.extents([ent])
            min_x, min_y = bb.extmin[0], bb.extmin[1]
            max_x, max_y = bb.extmax[0], bb.extmax[1]
        except Exception:
            continue

        all_mins.append((min_x, min_y))
        all_maxs.append((max_x, max_y))

        color = PIERCE_COLORS[i % len(PIERCE_COLORS)]
        rect = Rectangle((min_x, min_y), float(max_x - min_x), float(max_y - min_y), fill=False, edgecolor=color, linewidth=2.0, zorder=10)
        ax.add_patch(rect)
        # label with index
        ax.text(min_x + 0.01 * (max_x - min_x), max_y - 0.02 * (max_y - min_y), str(i), color=color, fontsize=10, zorder=11)

    # autoscale axes to include all boxes with some padding so labels are readable
    if all_mins and all_maxs:
        min_x = min(x for x, y in all_mins)
        min_y = min(y for x, y in all_mins)
        max_x = max(x for x, y in all_maxs)
        max_y = max(y for x, y in all_maxs)
        dx = max_x - min_x if max_x > min_x else 1.0
        dy = max_y - min_y if max_y > min_y else 1.0
        pad_x = dx * 0.05
        pad_y = dy * 0.05
        ax.set_xlim(min_x - pad_x, max_x + pad_x)
        ax.set_ylim(min_y - pad_y, max_y + pad_y)
    else:
        ax.autoscale()

    canvas = FigureCanvas(fig)
    buffer = io.BytesIO()
    canvas.print_png(buffer)
    return buffer.getvalue()
