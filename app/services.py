import math
import os
import shutil
import tempfile
from typing import List, Optional

from fastapi import UploadFile

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
