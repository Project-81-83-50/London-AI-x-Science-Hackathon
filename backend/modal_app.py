"""Modal deployment wrapper for exposing the FastAPI service as a cloud URL."""

from pathlib import Path

import modal

BACKEND_DIR = Path(__file__).parent.resolve()

# Build the Linux runtime from the backend dependencies and ship the API's Python code.
# The data/ and sem_pipeline/ folders the routes read are not part of the image.
image = (
    modal.Image.debian_slim()
    .pip_install_from_requirements(str(BACKEND_DIR / "app" / "requirements.txt"))
    .add_local_python_source("app")
)
app = modal.App("em-qc", image=image)


@app.function()
@modal.asgi_app()
def api():
    """Expose the existing FastAPI app through Modal's ASGI web endpoint."""
    from app.main import app as fastapi_app

    return fastapi_app
