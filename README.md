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

Then POST a DXF file to `http://localhost:8000/api/dxf/parse` with form fields:

- `file`: the DXF upload
- `unit`: one of `inches`, `millimeters`, `meters`, or `centimeters` describing the drawing's source units

### Rendering a preview image

You can also render the uploaded DXF to a PNG preview using the ezdxf drawing
addon. Send the DXF file to `http://localhost:8000/api/dxf/render` with the
same `file` form field and the `unit` selection. The response is an `image/png`
byte stream suitable for display or download.

If you need quick measurements for the rendered object, call
`http://localhost:8000/api/dxf/render/metrics` with the same upload and `unit`
field. The response includes maximum width/length in both millimeters and
inches, reported from ezdxf's bounding-box calculations.

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
