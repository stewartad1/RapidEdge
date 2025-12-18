from enum import Enum

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response

from .models import DxfDimensions, DxfParseResponse
from .services import (
    measure_dxf,
    parse_dxf,
    remove_file_safely,
    render_dxf_png,
    save_upload_to_temp,
    inspect_dxf,
    render_entity_bboxes,
)

router = APIRouter(prefix="/api/dxf", tags=["dxf"])


class DxfUnit(str, Enum):
    inches = "inches"
    millimeters = "millimeters"
    centimeters = "centimeters"
    meters = "meters"


def _validate_dxf_upload(file: UploadFile) -> None:
    # DXF uploads often come through as octet-stream from Swagger/curl
    if file.content_type not in {
        "application/dxf",
        "image/vnd.dxf",
        "application/octet-stream",
    }:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file type; please upload a DXF file.",
        )


@router.post("/parse", response_model=DxfParseResponse)
async def parse_dxf_upload(
    file: UploadFile = File(...),
    unit: DxfUnit = Form(DxfUnit.millimeters),
):
    _validate_dxf_upload(file)

    temp_path = None
    try:
        temp_path = await save_upload_to_temp(file)

        # Prefer passing unit through if services support it
        try:
            return parse_dxf(temp_path, file.filename, unit=unit.value)
        except TypeError:
            # Backwards-compatible: older parse_dxf signature
            return parse_dxf(temp_path, file.filename)

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    finally:
        if temp_path:
            remove_file_safely(temp_path)


@router.post("/render/metrics", response_model=DxfDimensions)
async def render_dxf_dimensions(
    file: UploadFile = File(...),
    unit: DxfUnit = Form(DxfUnit.millimeters),
):
    _validate_dxf_upload(file)

    temp_path = None
    try:
        temp_path = await save_upload_to_temp(file)

        # Prefer passing unit through if services support it
        try:
            return measure_dxf(temp_path, unit=unit.value)
        except TypeError:
            # Backwards-compatible: older measure_dxf signature
            return measure_dxf(temp_path)

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    finally:
        if temp_path:
            remove_file_safely(temp_path)


@router.post("/render", response_class=Response)
async def render_dxf_upload(
    file: UploadFile = File(...),
    unit: DxfUnit = Form(DxfUnit.millimeters),
):
    _validate_dxf_upload(file)

    temp_path = None
    try:
        temp_path = await save_upload_to_temp(file)

        # Render usually doesn't need units, but we accept it so Swagger shows it consistently.
        png_bytes = render_dxf_png(temp_path)
        return Response(content=png_bytes, media_type="image/png")

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    finally:
        if temp_path:
            remove_file_safely(temp_path)


@router.post("/inspect")
async def inspect_dxf_upload(
    file: UploadFile = File(...),
    join_tol: float = Form(0.0),
    unit: DxfUnit = Form(DxfUnit.millimeters),
):
    """Return structured diagnostic information about entities in the uploaded DXF.

    Useful for debugging pierce counts and identifying entity types/vertex counts.
    Accepts a 'unit' parameter (mm, in, etc.) to control output units for all lengths.
    """
    _validate_dxf_upload(file)

    temp_path = None
    try:
        temp_path = await save_upload_to_temp(file)
        return inspect_dxf(temp_path, join_tol=join_tol, unit=unit.value)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    finally:
        if temp_path:
            remove_file_safely(temp_path)


@router.post("/render/entity_bboxes", response_class=Response)
async def render_entity_bboxes_upload(
    file: UploadFile = File(...),
):
    """Return a PNG that overlays each entity's axis-aligned bounding box with a unique color."""
    _validate_dxf_upload(file)

    temp_path = None
    try:
        temp_path = await save_upload_to_temp(file)
        png_bytes = render_entity_bboxes(temp_path)
        return Response(content=png_bytes, media_type="image/png")
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    finally:
        if temp_path:
            remove_file_safely(temp_path)
