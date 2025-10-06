"""FastAPI entrypoint for the legal MVP service."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.routers import extract
from core import model


templates = Jinja2Templates(directory="app/templates")


@asynccontextmanager
async def lifespan(_: FastAPI):
    model.get_qa()
    model.get_ner()
    yield


app = FastAPI(title="legal-mvp", version="0.1.0", lifespan=lifespan)
app.include_router(extract.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
async def demo_page(request: Request) -> HTMLResponse:
    """Render the management-friendly demo dashboard."""
    return templates.TemplateResponse(request, "demo.html")


@app.get("/demo-guide", response_class=HTMLResponse)
async def demo_guide(request: Request) -> HTMLResponse:
    """Provide a short walkthrough for interview demos."""
    return templates.TemplateResponse(request, "demo_guide.html")
