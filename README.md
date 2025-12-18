# RapidEdge DXF Parser API

Backend service built with FastAPI that accepts DXF uploads and returns structured JSON with metadata, layers, entities, and bounds for frontend consumption.

## Setup

1. Move into the project root (in this container it's `/workspace/RapidEdge`; in Codespaces it may be `/workspaces/RapidEdge`), then create and activate a virtual environment (optional but recommended):
   ```bash
   cd /workspace/RapidEdge
   python -m venv .venv
   source .venv/bin/activate
   ```

2. Install dependencies (run this **from the project root** so `requirements.txt` is found). The requirements file now installs the local package in editable mode, making `app` importable during tests. Rendering support depends on `matplotlib` + `Pillow` from the same requirements file—if those optional packages cannot be installed, rendering tests will be skipped:
   ```bash
   # verify you're in /workspace/RapidEdge or /workspaces/RapidEdge
   ls requirements.txt
   pip install -r requirements.txt
   ```

## Running the server

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Then POST a DXF file to `http://localhost:8000/api/dxf/parse` with form field `file`.

### Rendering a preview image

You can also render the uploaded DXF to a PNG preview using the ezdxf drawing
addon. Send the DXF file to `http://localhost:8000/api/dxf/render` with the
same `file` form field. The response is an `image/png` byte stream suitable for
display or download.

If you need quick measurements for the rendered object, call
`http://localhost:8000/api/dxf/render/metrics` with the same upload. The
response includes several useful measurements in both millimeters and inches,
and a calculated bounding-box area in square inches, reported from ezdxf's
bounding-box calculations.

### Measurement fields explained 📐

- **object_width_in / _mm** and **object_length_in / _mm** — the object's
  primary dimensions (legacy semantics preserved). These are derived from the
  axis-aligned extents but named to make intent explicit: the *object* width is
  the larger of the X/Y extents and the *object* length is the smaller.
- **bbox_width_in / _mm** and **bbox_length_in / _mm** — the axis-aligned
  bounding-box X and Y extents as reported by ezdxf's `bbox.extents` helper.
  These are the raw extents in model space (rounded to 3 decimal places).
- **obb_width_in / _mm**, **obb_length_in / _mm**, **obb_angle_deg** — the
  **Oriented Bounding Box** (minimum-area rectangle). The OBB is the smallest
  area rectangle (any rotation) that contains the object; `obb_angle_deg` is
  the rotation (degrees CCW from the X axis).
- **min_max_rect_width_in / _mm**, **min_max_rect_length_in / _mm**,
  **min_max_rect_angle_deg** — the **min-max rectangle** minimizes the
  maximum side length (it selects the rectangle orientation that makes the
  largest side as small as possible). Useful when you care about the object's
  maximum dimension irrespective of orientation.
- **min_enclosing_square_side_in / _mm** — the side length of the **smallest
  axis-aligned square (after rotation) that contains the object**. For an
  equilateral triangle with side 3.21 in, this will be 3.21 in.
- **max_edge_length_in / _mm** — the length of the longest single straight
  segment present in the drawing (e.g., the longest LINE entity).
- **square_inches** — area of the axis-aligned bounding box in square inches.

Notes:
- All numeric measurements are rounded to at most **three** decimal places to
  avoid floating-point representation noise in the API responses.
- The `source_units` field reports the INSUNITS drawing units (if present).

### Disable the blue bounding box in rendered PNGs 🔵➡️❌

By default rendered PNGs annotate the drawing with:
- object lines recolored **green** and
- an axis-aligned bounding box drawn in **blue**.

You can disable the blue bounding box with a single-line change in the code:

```py
# in app/services.py near the top of the file
DRAW_BBOX = True  # set to False to disable drawing the blue bbox
```

After changing it to `False`, restart the server and PNG renders will no
longer draw the blue bounding box (object lines remain green).

---


## Testing

```bash
pytest
```

## Publishing your local branch to GitHub

The repository in this environment is local-only by default. To push the existing
`work` branch (and its files) to your GitHub account:

1. Create a new empty repository on GitHub (no README/license) and copy its SSH or HTTPS URL.
2. Add it as a remote from the project root:
   ```bash
   git remote add origin <your-github-repo-url>
   ```
3. Push the current branch to GitHub (create the remote branch if it doesn't exist):
   ```bash
   git push -u origin work
   ```
After pushing, the files you see locally will appear in your GitHub repository, and you can open a PR from there.

## Project structure

```
app/
  main.py          # FastAPI application entry
  models.py        # Pydantic schemas
  services.py      # DXF parsing helpers
  routers.py       # API routing for DXF parsing
samples/           # Sample DXF files for tests
tests/             # Automated tests
```
