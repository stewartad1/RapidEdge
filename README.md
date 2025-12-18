# RapidEdge DXF Parser API

Backend service built with FastAPI that accepts DXF uploads and returns structured JSON with metadata, layers, entities, and bounds for frontend consumption.

## Setup

1. Move into the project root (in this container it's `/workspace/RapidEdge`; in Codespaces it may be `/workspaces/RapidEdge`), then create and activate a virtual environment (optional but recommended):
   ```bash
   cd /workspaces/RapidEdge
   python -m venv .venv
   source .venv/bin/activate
   ```

2. Install dependencies (run this **from the project root** so `requirements.txt` is found). The requirements file now installs the local package in editable mode, making `app` importable during tests. Rendering support depends on `matplotlib` + `Pillow` from the same requirements file—if those optional packages cannot be installed, rendering tests will be skipped:
   ```bash
   # verify you're in /workspaces/RapidEdge or /workspaces/RapidEdge
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


By default, rendered PNGs annotate the drawing with:
- all object lines recolored **green** (single color for all pierces)
- an axis-aligned bounding box drawn in **blue**.

To enable per-pierce coloring (each unbroken entity gets a different color), set the following in `app/services.py` and restart the server:

```py
# in app/services.py near the top of the file
COLOR_EACH_PIERCE = True    # set to True to color each pierce differently
```

Other annotation behaviors are controlled by single-line toggles in the code:

```py
DRAW_BBOX = True            # set to False to disable drawing the blue bbox
```

After changing either flag, restart the server and PNG renders will reflect the new behavior (the change is code-level only and will not appear as a control in Swagger/OpenAPI docs).

---

## Diagnostics and Troubleshooting

### Inspecting pierce counts and connectivity

- **POST `/api/dxf/inspect`** — returns JSON diagnostics:
  - `counts`: per-entity-type counts
  - `number_of_pierces`: raw sum of LINE, ARC, CIRCLE, POLYLINE, LWPOLYLINE
  - `connected_pierces`: number of connected components (entities joined by endpoints)
  - `entities`: per-entity info (type, bbox, vertex count, summary)
  - `components`: list of entity indices per connected pierce
  - **Form parameter:** `join_tol` (float, default `0.0`) — tolerance (model units) for merging near-touching endpoints
  - Example:
    ```bash
    curl -F "file=@YourFav.dxf" -F "join_tol=0.03" http://localhost:8000/api/dxf/inspect
    ```

- **POST `/api/dxf/render/entity_bboxes`** — returns a PNG with a colored axis-aligned bounding box and index for each entity, to visually locate entities as reported by `/api/dxf/inspect`.

### Counting semantics
- **Raw pierce count**: `number_of_pierces` = sum of LINE/CIRCLE/ARC/POLYLINE entities (conservative).
- **Connected pierces**: `connected_pierces` merges entities that are contiguous (share endpoints). By default this requires exact zero disconnect (`join_tol=0.0`). Increase `join_tol` to merge near-touching endpoints (e.g., `0.02`–`0.04`) to treat small gaps as continuous pierces.

---

### Entity lengths and total length

- **POST `/api/dxf/inspect`** now also returns:
  - For each entity: a `length` field (in the selected output unit) for every LINE, ARC, CIRCLE, POLYLINE, or LWPOLYLINE (computed using geometry).
  - `total_line_length`: the sum of all such entity lengths in the file (in the selected output unit).
  - `output_units`: the unit used for all length fields (matches the `unit` form parameter; default is `millimeters`).

**Form parameter:** `unit` (default: `millimeters`). Accepts: `millimeters`, `inches`, `centimeters`, `meters`.

Example response fields:
```json
{
  ...,
  "entities": [
    {"index": 0, "type": "LINE", ..., "length": 12.34},
    {"index": 1, "type": "ARC", ..., "length": 5.67},
    ...
  ],
  "total_line_length": 123.45,
  "output_units": "millimeters"
}
```

This helps you quickly see the length of each cuttable entity and the total length for quoting or process planning.

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
