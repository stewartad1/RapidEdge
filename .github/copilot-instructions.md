# Project goal
Build a web app backend that accepts a DXF upload, parses it, and returns a structured JSON description
(entities, layers, bounding boxes, units/metadata) suitable for a frontend viewer.

# Tech choices
- Backend: Python + FastAPI.
- DXF parsing: use a proven library; **ezdxf is required**. Do NOT build a DXF parser from scratch.
- Pin DXF dependency versions (e.g., specify an ezdxf version range) in requirements.
- Data model: Pydantic models for request/response.

# API expectations
- POST /api/dxf/parse : multipart upload "file"
  - returns JSON: { metadata, layers[], entities[], bounds }
- Validate file type/size; never execute embedded content.
- Return API errors using FastAPI `HTTPException` with clear, user-friendly messages (and appropriate status codes).
- If storing files, use temp storage with cleanup; avoid long-term persistence by default.

# Quality bar
- Add unit tests for parsing on at least 2 sample DXF files in /samples.
- Prefer clear, readable code over cleverness.
- Include a short README section for running locally and testing.
