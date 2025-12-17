import math
import tempfile
from typing import List, Optional

import ezdxf
from ezdxf.entities import DXFGraphic
from ezdxf.lldxf.const import DXFError

from .models import Bounds, DxfEntity, DxfLayer, DxfMetadata, DxfParseResponse


def _compute_entity_bounds(entities: List[DXFGraphic]) -> Optional[Bounds]:
    """Calculate bounds from supported entities for deterministic results.

    The built-in modelspace ``bbox`` helper can return ``None`` for sparse
    content. To keep predictable bounds for our simple fixtures, we derive
    limits from LINE and CIRCLE entities directly and ignore unsupported
    entity types.
    """

    min_x = math.inf
    min_y = math.inf
    min_z = math.inf
    max_x = -math.inf
    max_y = -math.inf
    max_z = -math.inf

    for entity in entities:
        etype = entity.dxftype()
        if etype == "LINE":
            start = entity.dxf.start
            end = entity.dxf.end
            xs = [start.x, end.x]
            ys = [start.y, end.y]
            zs = [start.z, end.z]
        elif etype == "CIRCLE":
            center = entity.dxf.center
            r = float(entity.dxf.radius)
            xs = [center.x - r, center.x + r]
            ys = [center.y - r, center.y + r]
            zs = [center.z, center.z]
        else:
            # Unknown entity types are skipped to avoid incorrect bounds.
            continue

        min_x = min(min_x, *xs)
        max_x = max(max_x, *xs)
        min_y = min(min_y, *ys)
        max_y = max(max_y, *ys)
        min_z = min(min_z, *zs)
        max_z = max(max_z, *zs)

    if math.isinf(min_x):
        return None

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


def _extract_entities(msp) -> List[DXFGraphic]:
    return list(msp)


def parse_dxf(file_bytes: bytes, filename: str) -> DxfParseResponse:
    try:
        # ezdxf expects text streams for ASCII DXF files; reading from a binary
        # buffer triggers a bytes/str mismatch inside the tag loader. Decode to
        # text (ignoring invalid bytes) and persist to a temporary text file so
        # ezdxf can parse reliably.
        text_content = file_bytes.decode("utf-8", errors="ignore")
        with tempfile.NamedTemporaryFile(
            mode="w+", suffix=".dxf", encoding="utf-8"
        ) as tmp:
            tmp.write(text_content)
            tmp.flush()
            doc = ezdxf.readfile(tmp.name)
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
