from fastapi import APIRouter, HTTPException, UploadFile, status

from .models import DxfParseResponse
from .services import parse_dxf

router = APIRouter(prefix="/api/dxf", tags=["dxf"])


@router.post("/parse", response_model=DxfParseResponse)
async def parse_dxf_upload(file: UploadFile):
    if file.content_type not in {"application/dxf", "image/vnd.dxf", "application/octet-stream"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file type; please upload a DXF file.",
        )

    content = await file.read()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    try:
        return parse_dxf(content, file.filename)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
