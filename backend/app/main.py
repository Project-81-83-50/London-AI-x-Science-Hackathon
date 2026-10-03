"""FastAPI app: CORS setup and the API routers (one per frontend feature, see app/routers/)."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import get4, images, kpi, lucas, mock, unknown

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

for module in (mock, get4, kpi, unknown, lucas, images):
    app.include_router(module.router)


if __name__ == "__main__":
    import uvicorn
    # Running this module directly starts the local development API on port 8000.
    uvicorn.run(app, host="0.0.0.0", port=8000)
