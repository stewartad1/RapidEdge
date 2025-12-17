from typing import List, Optional

from pydantic import BaseModel, Field


class Bounds(BaseModel):
    min_x: float
    min_y: float
    min_z: float
    max_x: float
    max_y: float
    max_z: float


class DxfMetadata(BaseModel):
    filename: str
    version: str
    units: Optional[int] = Field(
        None,
        description="DXF insertion units code; see AutoCAD INSUNITS codes",
    )


class DxfLayer(BaseModel):
    name: str
    color: Optional[int] = None


class DxfEntity(BaseModel):
    type: str
    layer: Optional[str] = None


class DxfParseResponse(BaseModel):
    metadata: DxfMetadata
    layers: List[DxfLayer]
    entities: List[DxfEntity]
    bounds: Optional[Bounds]
