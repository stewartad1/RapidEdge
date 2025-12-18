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

    return DxfParseResponse(
        metadata=metadata,
        layers=layers,
        entities=entities,
        bounds=bounds,
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

    - Recolors existing line artists and collections to `object_color`.
    - Adds an axis-aligned rectangle from `extmin` to `extmax` in `bbox_color`.
    """
    try:
        import matplotlib
        from matplotlib.patches import Rectangle
        from matplotlib.colors import to_rgba
    except Exception:  # pragma: no cover - defensive
        return

    # Recolor lines
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

    # Draw axis-aligned bounding box and recolor objects
    try:
        from ezdxf import bbox as ez_bbox
        bbox = ez_bbox.extents(msp)
        if DRAW_BBOX:
            _annotate_bbox(ax, bbox.extmin, bbox.extmax, object_color="green", bbox_color="blue")
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
