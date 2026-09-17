"""Same-origin local playground UI plus content-free debug read APIs."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from app.config import settings
from app.errors import AuthenticationError
from app.observability import recent_requests, summary

router = APIRouter()

_STATIC_DIR = Path(__file__).resolve().parent / "static"
_ASSETS = {
    "app.js": "application/javascript; charset=utf-8",
    "ui.js": "application/javascript; charset=utf-8",
    "vision.js": "application/javascript; charset=utf-8",
    "markdown.js": "application/javascript; charset=utf-8",
    "prose.js": "application/javascript; charset=utf-8",
    "styles.css": "text/css; charset=utf-8",
    "polish.css": "text/css; charset=utf-8",
}
_SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "Content-Security-Policy": (
        "default-src 'self'; connect-src 'self'; img-src 'self' data: blob:; "
        "style-src 'self'; script-src 'self'; base-uri 'none'; "
        "frame-ancestors 'none'; form-action 'self'"
    ),
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
}


def _authenticate(key: str | None) -> None:
    """Protect debug data with the gateway's existing local API key."""

    if key != settings.gateway_api_key:
        raise AuthenticationError()


@router.get("/playground", include_in_schema=False)
async def playground_redirect() -> RedirectResponse:
    """Use a stable trailing-slash URL so relative UI assets resolve predictably."""

    return RedirectResponse(url="/playground/", status_code=307)


@router.get("/playground/", include_in_schema=False)
async def playground_index() -> HTMLResponse:
    """Serve the zero-build local shell and mount Stage 5 extensions."""

    html = (_STATIC_DIR / "index.html").read_text(encoding="utf-8")
    marker = '  <script src="/playground/assets/app.js" defer></script>'
    extensions = [
        '  <script src="/playground/assets/markdown.js" defer></script>',
        '  <script src="/playground/assets/prose.js" defer></script>',
        '  <script src="/playground/assets/vision.js" defer></script>',
    ]
    for script in reversed(extensions):
        if script not in html:
            html = html.replace(marker, f"{script}\n{marker}")
    return HTMLResponse(
        content=html,
        media_type="text/html",
        headers=_SECURITY_HEADERS,
    )


@router.get("/playground/assets/{asset_name}", include_in_schema=False)
async def playground_asset(asset_name: str) -> FileResponse:
    """Serve allow-listed static assets and reject path traversal/unknown files."""

    media_type = _ASSETS.get(asset_name)
    if media_type is None:
        raise HTTPException(status_code=404, detail="Playground asset not found.")
    return FileResponse(
        _STATIC_DIR / asset_name,
        media_type=media_type,
        headers={"Cache-Control": "no-cache", "X-Content-Type-Options": "nosniff"},
    )


@router.get("/v1/debug/metrics")
async def debug_metrics_endpoint(
    days: int = Query(default=7, ge=1, le=365),
    x_local_ai_key: str | None = Header(default=None),
) -> dict:
    """Return aggregate, non-content gateway metrics for local debugging."""

    _authenticate(x_local_ai_key)
    return summary(days=days)


@router.get("/v1/debug/requests")
async def debug_requests_endpoint(
    limit: int = Query(default=50, ge=1, le=200),
    x_local_ai_key: str | None = Header(default=None),
) -> dict:
    """Return recent request metadata without prompt, response, RAG, or tool content."""

    _authenticate(x_local_ai_key)
    return {"requests": recent_requests(limit=limit)}
