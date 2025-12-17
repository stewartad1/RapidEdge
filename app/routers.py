import os

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from .models import DxfParseResponse
from .services import parse_dxf, remove_file_safely, save_upload_to_temp

router = APIRouter(prefix="/api/dxf", tags=["dxf"])


@router.post("/parse", response_model=DxfParseResponse)
async def parse_dxf_upload(file: UploadFile = File(...)):
    if file.content_type not in {"application/dxf", "image/vnd.dxf", "application/octet-stream"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file type; please upload a DXF file.",
        )

    temp_path = await save_upload_to_temp(file)
    try:
        if os.path.getsize(temp_path) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file is empty.",
            )

        return parse_dxf(temp_path, file.filename)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    finally:
        remove_file_safely(temp_path)
