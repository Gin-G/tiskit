"""tiskit — HIPAA-conscious PDF template analyzer.

Design rules:
- PDFs never touch the disk. All processing is in-memory and the buffers
  are dropped as soon as the response is returned.
- No request bodies or filenames are logged. Access logs are off.
- Strict security headers are applied at the app layer as defense-in-depth
  on top of the Traefik middleware.
"""

from __future__ import annotations

import logging
import os
import secrets
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from pdf_analyzer import AnalyzeError, analyze_pdf_template

MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(25 * 1024 * 1024)))
PDF_MAGIC = b"%PDF-"

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format='{"ts":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}',
)
log = logging.getLogger("tiskit")

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(
    title="tiskit",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adds HIPAA-relevant response headers on every response."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        h = response.headers
        h["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
        h["X-Content-Type-Options"] = "nosniff"
        h["X-Frame-Options"] = "DENY"
        h["Referrer-Policy"] = "no-referrer"
        h["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0, private"
        h["Pragma"] = "no-cache"
        h["Expires"] = "0"
        h["Permissions-Policy"] = "geolocation=(), microphone=(), camera=(), payment=()"
        h["Content-Security-Policy"] = (
            "default-src 'self'; "
            "style-src 'self'; "
            "script-src 'self'; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'none'; "
            "form-action 'self'"
        )
        h["X-Robots-Tag"] = "noindex, nofollow"
        # Don't leak framework identity
        if "server" in h:
            del h["server"]
        return response


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Attach a request id for correlated audit logs (no PHI)."""

    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response


app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestIdMiddleware)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.get("/healthz", include_in_schema=False)
async def healthz():
    return JSONResponse({"ok": True})


@app.get("/readyz", include_in_schema=False)
async def readyz():
    return JSONResponse({"ok": True})


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


async def _read_pdf(upload: UploadFile) -> bytes:
    """Stream the upload into memory with a hard size cap. No disk spill."""
    if upload.content_type and upload.content_type != "application/pdf":
        raise HTTPException(status_code=415, detail="Only application/pdf is accepted.")

    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(64 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_UPLOAD_BYTES:
            # Drop what we've read so it can be GC'd promptly.
            chunks.clear()
            raise HTTPException(status_code=413, detail="File exceeds maximum allowed size.")
        chunks.append(chunk)

    data = b"".join(chunks)
    chunks.clear()
    if not data.startswith(PDF_MAGIC):
        raise HTTPException(status_code=415, detail="File is not a valid PDF.")
    return data


@app.post("/api/templates/analyze")
async def analyze_template(request: Request, file: UploadFile = File(...)):
    rid = request.headers.get("X-Request-ID", "-")
    data = await _read_pdf(file)
    try:
        result = analyze_pdf_template(data)
    except AnalyzeError as exc:
        log.warning("analyze_failed rid=%s reason=%s", rid, exc.code)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        # Best-effort scrub: drop the only reference we hold.
        data = b""
        del data

    log.info(
        "analyze_ok rid=%s pages=%s fields=%s has_form=%s",
        rid,
        result["page_count"],
        result["field_count"],
        result["has_acroform"],
    )
    # Add a per-response nonce so the client can correlate without us logging anything sensitive.
    result["nonce"] = secrets.token_urlsafe(8)
    return JSONResponse(result)
