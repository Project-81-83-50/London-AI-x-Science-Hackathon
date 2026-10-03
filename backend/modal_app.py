"""Modal deployment wrapper for exposing the FastAPI service as a cloud URL."""

import modal
from pathlib import Path

BACKEND_DIR = Path(__file__).parent.resolve()

# Build the Linux runtime from the backend dependencies and ship its Python code
# plus the JSON samples that the API reads at request time.
image = (modal.Image.debian_slim()
         .pip_install_from_requirements(str(BACKEND_DIR / "app" / "requirements.txt"))
         .add_local_python_source("app")
         .add_local_dir(str(BACKEND_DIR / "app" / "mock"), remote_path="/root/app/mock"))
app = modal.App("em-qc", image=image)

@app.function()
@modal.asgi_app()
def api():
    """Expose the existing FastAPI app through Modal's ASGI web endpoint."""
    from app.main import app as fastapi_app
    return fastapi_app