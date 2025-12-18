import os

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response

from .models import DxfDimensions, DxfParseResponse
from .services import (
    measure_dxf,
    parse_dxf,
    remove_file_safely,
    render_dxf_png,
    save_upload_to_temp,
    UserUnit,
)

router = APIRouter(prefix="/api/dxf", tags=["dxf"])


@router.post("/parse", response_model=DxfParseResponse)
async def parse_dxf_upload(
    file: UploadFile = File(...),
    unit: UserUnit = Form(
        "millimeters",
        description="Unit of measure for the DXF file.",
    ),
):
    if file.content_type not in {"application/dxf", "image/vnd.dxf", "application/octet-stream"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file type; please upload a DXF file.",
        )

    temp_path = None
    try:
        temp_path = await save_upload_to_temp(file)
        return parse_dxf(temp_path, file.filename, unit)
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
    unit: UserUnit = Form(
        "millimeters",
        description="Unit of measure for the DXF file.",
    ),
):
    if file.content_type not in {"application/dxf", "image/vnd.dxf", "application/octet-stream"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file type; please upload a DXF file.",
        )

    temp_path = None
    try:
        temp_path = await save_upload_to_temp(file)
        return measure_dxf(temp_path, unit)
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
    unit: UserUnit = Form(
        "millimeters",
        description="Unit of measure for the DXF file.",
    ),
):
    if file.content_type not in {"application/dxf", "image/vnd.dxf", "application/octet-stream"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file type; please upload a DXF file.",
        )

    temp_path = None
    try:
        temp_path = await save_upload_to_temp(file)
        png_bytes = render_dxf_png(temp_path, unit)
        return Response(content=png_bytes, media_type="image/png")
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    finally:
        if temp_path:
            remove_file_safely(temp_path)
