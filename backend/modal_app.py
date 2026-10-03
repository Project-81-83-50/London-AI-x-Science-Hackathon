import modal
from pathlib import Path

BACKEND_DIR = Path(__file__).parent.resolve()

image = (modal.Image.debian_slim()
         .pip_install_from_requirements(str(BACKEND_DIR / "app" / "requirements.txt"))
         .add_local_python_source("app")
         .add_local_dir(str(BACKEND_DIR / "app" / "mock"), remote_path="/root/app/mock"))
app = modal.App("em-qc", image=image)

@app.function()
@modal.asgi_app()
def api():
    from app.main import app as fastapi_app
    return fastapi_app