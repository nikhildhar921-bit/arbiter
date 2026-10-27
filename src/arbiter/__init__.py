import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from arbiter.controllers.processdata import keepRunning
from arbiter.routers import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    publisher_task = asyncio.create_task(keepRunning())
    yield
    publisher_task.cancel()


app = FastAPI(lifespan=lifespan)
app.include_router(router)

__all__ = ["app"]