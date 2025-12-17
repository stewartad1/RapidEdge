import io
from typing import List, Optional

import ezdxf
from ezdxf.entities import DXFGraphic
from ezdxf.lldxf.const import DXFError

from .models import Bounds, DxfEntity, DxfLayer, DxfMetadata, DxfParseResponse


def _extract_bounds(msp) -> Optional[Bounds]:
    bbox = msp.bbox()
    if bbox is None:
        return None

    (min_x, min_y, min_z), (max_x, max_y, max_z) = bbox.extmin, bbox.extmax
    return Bounds(
        min_x=float(min_x),
        min_y=float(min_y),
        min_z=float(min_z),
        max_x=float(max_x),
        max_y=float(max_y),
        max_z=float(max_z),
    )


def _extract_layers(doc) -> List[DxfLayer]:
    return [
        DxfLayer(name=layer.dxf.name, color=layer.color)
        for layer in doc.layers
    ]


def _extract_entities(msp) -> List[DxfEntity]:
    entities: List[DXFGraphic] = list(msp)
    return [
        DxfEntity(type=entity.dxftype(), layer=entity.dxf.layer)
        for entity in entities
    ]


def parse_dxf(file_bytes: bytes, filename: str) -> DxfParseResponse:
    try:
        doc = ezdxf.read(stream=io.BytesIO(file_bytes))
    except (DXFError, IOError) as exc:  # DXFError for invalid files
        raise ValueError(f"Invalid DXF file: {exc}") from exc

    msp = doc.modelspace()
    metadata = DxfMetadata(
        filename=filename,
        version=doc.acad_release,
        units=doc.header.get("$INSUNITS"),
    )

    layers = _extract_layers(doc)
    entities = _extract_entities(msp)
    bounds = _extract_bounds(msp)

    return DxfParseResponse(
        metadata=metadata,
        layers=layers,
        entities=entities,
        bounds=bounds,
    )
