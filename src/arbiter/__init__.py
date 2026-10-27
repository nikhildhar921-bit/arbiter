import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from arbiter.controllers.processdata import keepRunning
from arbiter.routers import router

BASE_DIR = Path(__file__).resolve().parent.parent.parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    publisher_task = asyncio.create_task(keepRunning())
    yield
    publisher_task.cancel()


app = FastAPI(lifespan=lifespan)
app.include_router(router)
app.mount("/samples", StaticFiles(directory=BASE_DIR / "sample-documents"), name="samples")


@app.get("/", include_in_schema=False)
async def demo_page():
    return FileResponse(BASE_DIR / "static" / "index.html")


__all__ = ["app"]