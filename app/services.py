import io
import os
import tempfile
from typing import TYPE_CHECKING, Dict, List, Optional

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
    UnitOfMeasure,
)

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
    """

    from ezdxf import bbox as ez_bbox

    try:
        bbox = ez_bbox.extents(entities)
    except ez_bbox.BoundingBoxError:
        return None

    return Bounds(
        min_x=float(bbox.extmin[0]),
        min_y=float(bbox.extmin[1]),
        min_z=float(bbox.extmin[2]),
        max_x=float(bbox.extmax[0]),
        max_y=float(bbox.extmax[1]),
        max_z=float(bbox.extmax[2]),
    )


def _extract_layers(doc) -> List[DxfLayer]:
    return [
        DxfLayer(name=layer.dxf.name, color=layer.color)
        for layer in doc.layers
    ]


def _extract_entities(msp) -> List[DXFGraphic]:
    return list(msp)


def _unit_code(unit: UnitOfMeasure) -> int:
    from ezdxf import units as ez_units

    unit_map: Dict[UnitOfMeasure, int] = {
        UnitOfMeasure.MILLIMETERS: ez_units.InsertUnits.Millimeters.value,
        UnitOfMeasure.INCHES: ez_units.InsertUnits.Inches.value,
        UnitOfMeasure.CENTIMETERS: ez_units.InsertUnits.Centimeters.value,
        UnitOfMeasure.METERS: ez_units.InsertUnits.Meters.value,
    }

    return unit_map[unit]


def _resolve_base_unit(raw_units: int, fallback_unit: Optional[UnitOfMeasure]) -> int:
    from ezdxf import units as ez_units

    if raw_units > 0:
        return raw_units

    if fallback_unit is not None:
        return _unit_code(fallback_unit)

    return ez_units.InsertUnits.Millimeters.value


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


def measure_dxf(file_path: str, fallback_unit: Optional[UnitOfMeasure] = None) -> DxfDimensions:
    """Calculate maximum width/length in both millimeters and inches.

    A ``fallback_unit`` can be provided when the DXF file does not declare an
    ``$INSUNITS`` header, allowing callers (and Swagger users) to choose how to
    interpret the raw coordinates.
    """

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

    width = float(bbox.extmax[0] - bbox.extmin[0])
    length = float(bbox.extmax[1] - bbox.extmin[1])

    raw_units = int(doc.header.get("$INSUNITS", 0) or 0)
    base_unit_value = _resolve_base_unit(raw_units, fallback_unit)

    def _convert(value: float, target: int) -> float:
        factor = ez_units.conversion_factor(base_unit_value, target)
        return float(value * factor)

    width_mm = _convert(width, ez_units.MM)
    length_mm = _convert(length, ez_units.MM)
    width_in = _convert(width, ez_units.IN)
    length_in = _convert(length, ez_units.IN)

    unit_label = ez_units.InsertUnits(base_unit_value).name

    return DxfDimensions(
        width_mm=width_mm,
        width_in=width_in,
        length_mm=length_mm,
        length_in=length_in,
        source_units=unit_label,
    )


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
