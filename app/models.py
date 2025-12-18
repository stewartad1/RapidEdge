from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class UnitOfMeasure(str, Enum):
    INCHES = "inches"
    MILLIMETERS = "millimeters"
    CENTIMETERS = "centimeters"
    METERS = "meters"


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


class DxfDimensions(BaseModel):
    width_mm: float = Field(..., description="Maximum width of the drawing in millimeters")
    width_in: float = Field(..., description="Maximum width of the drawing in inches")
    length_mm: float = Field(..., description="Maximum length of the drawing in millimeters")
    length_in: float = Field(..., description="Maximum length of the drawing in inches")
    source_units: str = Field(
        ..., description="Resolved drawing units from DXF INSUNITS or a requested override"
    )


class DxfParseResponse(BaseModel):
    metadata: DxfMetadata
    layers: List[DxfLayer]
    entities: List[DxfEntity]
    bounds: Optional[Bounds]
