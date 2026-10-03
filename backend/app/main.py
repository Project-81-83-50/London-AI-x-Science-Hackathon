"""FastAPI routes for listing material batches and retrieving their analysis."""

import json
import re
from io import BytesIO
from pathlib import Path
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from PIL import Image
from .schemas import Analysis, BatchSummary

app = FastAPI(title="EM QC API")

# Allow the local Vite page and other frontends to call this API during development.
# For a public production deployment, replace "*" with the approved frontend origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

MOCK_DIR = Path(__file__).parent / "mock"
RAW_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"
IMAGE_NAME_PATTERN = re.compile(
    r"^img_(?P<specimen>.+?)_(?P<filter>BSE|ETD|Inlens)(?:\s+\(\d+\))?\.tif$",
    re.IGNORECASE,
)

def load_mock(batch_id: str) -> dict:
    """Load one batch's sample analysis JSON, or return HTTP 404 if it is unknown."""
    path = MOCK_DIR / f"{batch_id}.json"
    if not path.exists():
        raise HTTPException(404, f"Unknown batch {batch_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def get_batch_image_directory(batch_id: str) -> Path:
    """Return a valid local raw-image directory for a numeric batch ID."""
    if not batch_id.isdigit():
        raise HTTPException(404, f"Unknown image batch {batch_id}")
    directory = RAW_DATA_DIR / f"batch_{batch_id}"
    if not directory.is_dir():
        raise HTTPException(404, f"Image directory for batch {batch_id} was not found")
    return directory


def find_batch_image(batch_id: str, image_name: str) -> Path:
    """Resolve an image name only when it matches an indexed file in its batch."""
    directory = get_batch_image_directory(batch_id)
    for path in directory.iterdir():
        if path.is_file() and path.name == image_name and IMAGE_NAME_PATTERN.fullmatch(path.name):
            return path
    raise HTTPException(404, f"Unknown image {image_name} in batch {batch_id}")


@app.get("/batches", response_model=list[BatchSummary])
def list_batches():
    """Return one compact summary for every JSON batch in the mock-data folder."""
    return [load_mock(p.stem) for p in sorted(MOCK_DIR.glob("*.json"))]

@app.get("/batches/{batch_id}/analysis", response_model=Analysis)
def get_analysis(batch_id: str):
    """Return the full analysis record for the requested batch ID."""
    return load_mock(batch_id)


@app.get("/batches/{batch_id}/images")
def list_batch_images(batch_id: str):
    """List local TIFF views grouped by their shared specimen identifier."""
    directory = get_batch_image_directory(batch_id)
    groups: dict[str, list[dict[str, str]]] = {}
    for path in sorted(directory.iterdir()):
        match = IMAGE_NAME_PATTERN.fullmatch(path.name)
        if path.is_file() and match:
            specimen_id = match.group("specimen")
            groups.setdefault(specimen_id, []).append(
                {"filter": match.group("filter"), "filename": path.name}
            )
    return [
        {"specimen_id": specimen_id, "images": images}
        for specimen_id, images in sorted(groups.items())
    ]


@app.get("/batches/{batch_id}/images/{image_name}")
def get_batch_image(
    batch_id: str,
    image_name: str,
    download: bool = Query(default=False),
):
    """Serve a browser-friendly JPEG preview or the original TIFF download."""
    path = find_batch_image(batch_id, image_name)
    if download:
        return FileResponse(path, media_type="image/tiff", filename=path.name)

    try:
        with Image.open(path) as image:
            image.thumbnail((1800, 1200), Image.Resampling.LANCZOS)
            preview = image.convert("RGB")
            output = BytesIO()
            preview.save(output, format="JPEG", quality=88, optimize=True)
    except OSError as error:
        raise HTTPException(500, f"Could not decode image {image_name}") from error

    return Response(
        content=output.getvalue(),
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=3600"},
    )


if __name__ == "__main__":
    import uvicorn
    # Running this module directly starts the local development API on port 8000.
    uvicorn.run(app, host="0.0.0.0", port=8000)