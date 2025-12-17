from fastapi import FastAPI

from .routers import router as dxf_router

app = FastAPI(title="RapidEdge DXF Parser")
app.include_router(dxf_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
