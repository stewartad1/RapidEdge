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


class DxfDimensions(BaseModel):
    # Object dimensions (legacy semantics preserved but renamed to be explicit)
    object_width_mm: float = Field(..., description="Object width in millimeters")
    object_width_in: float = Field(..., description="Object width in inches")
    object_length_mm: float = Field(..., description="Object length in millimeters")
    object_length_in: float = Field(..., description="Object length in inches")

    # Axis-aligned bounding-box dimensions (explicit)
    bbox_width_mm: float = Field(..., description="Bounding box width (X extent) in millimeters")
    bbox_width_in: float = Field(..., description="Bounding box width (X extent) in inches")
    bbox_length_mm: float = Field(..., description="Bounding box length (Y extent) in millimeters")
    bbox_length_in: float = Field(..., description="Bounding box length (Y extent) in inches")

    square_inches: float = Field(
        ...,
        description="Calculated area of the bounding box in square inches",
    )

    # Largest single edge length present in the drawing (e.g., longest LINE)
    max_edge_length_mm: float = Field(
        ..., description="Maximum single-segment edge length in millimeters"
    )
    max_edge_length_in: float = Field(
        ..., description="Maximum single-segment edge length in inches"
    )

    # Oriented bounding box (minimum-area rectangle) properties
    obb_width_mm: float = Field(
        ..., description="OBB width (longer side) in millimeters"
    )
    obb_width_in: float = Field(
        ..., description="OBB width (longer side) in inches"
    )
    obb_length_mm: float = Field(
        ..., description="OBB length (shorter side) in millimeters"
    )
    obb_length_in: float = Field(
        ..., description="OBB length (shorter side) in inches"
    )
    obb_angle_deg: float = Field(
        ..., description="Rotation angle of the OBB in degrees (CCW from X axis)"
    )

    # Minimum maximum-side rectangle (minimize max(width, length)) and
    # minimal enclosing square side (smallest square side that contains the object)
    min_max_rect_width_mm: float = Field(
        ..., description="Min-max-rect width (longer side) in millimeters"
    )
    min_max_rect_width_in: float = Field(
        ..., description="Min-max-rect width (longer side) in inches"
    )
    min_max_rect_length_mm: float = Field(
        ..., description="Min-max-rect length (shorter side) in millimeters"
    )
    min_max_rect_length_in: float = Field(
        ..., description="Min-max-rect length (shorter side) in inches"
    )
    min_max_rect_angle_deg: float = Field(
        ..., description="Rotation angle of the min-max rectangle in degrees (CCW from X axis)"
    )

    min_enclosing_square_side_mm: float = Field(
        ..., description="Side length of the minimal enclosing square in millimeters"
    )
    min_enclosing_square_side_in: float = Field(
        ..., description="Side length of the minimal enclosing square in inches"
    )

    source_units: str = Field(
        ..., description="Drawing units reported from the DXF INSUNITS header value"
    )


class DxfParseResponse(BaseModel):
    metadata: DxfMetadata
    layers: List[DxfLayer]
    entities: List[DxfEntity]
    bounds: Optional[Bounds]

    # Counts for different unbroken line entity types
    number_of_lines: int = Field(..., description="Count of LINE entities")
    number_of_circles: int = Field(..., description="Count of CIRCLE entities")
    number_of_arcs: int = Field(..., description="Count of ARC entities")
    number_of_polylines: int = Field(..., description="Count of POLYLINE/LWPOLYLINE entities")

    # Total count of unbroken lines (used for pierces)
    number_of_pierces: int = Field(
        ..., description="Total count of unbroken line-like entities (lines, circles, arcs, polylines)"
    )
