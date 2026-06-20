from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, HTMLResponse, Response

router = APIRouter(tags=["ops-ui"])


@router.get("/ops", response_class=HTMLResponse)
def ops_index() -> Response:
    dist_index = _frontend_dist() / "index.html"
    if dist_index.exists():
        return FileResponse(dist_index)
    html_path = _legacy_ops_html()
    return HTMLResponse(html_path.read_text())


@router.get("/ops/{asset_path:path}")
def ops_asset(asset_path: str) -> Response:
    dist = _frontend_dist()
    target = (dist / asset_path).resolve()
    if dist.exists() and target.is_file() and target.is_relative_to(dist.resolve()):
        return FileResponse(target)
    dist_index = dist / "index.html"
    if dist_index.exists():
        return FileResponse(dist_index)
    return HTMLResponse(_legacy_ops_html().read_text())


def _frontend_dist() -> Path:
    return Path(__file__).resolve().parents[4] / "frontend" / "dist"


def _legacy_ops_html() -> Path:
    return Path(__file__).resolve().parents[1] / "static" / "ops.html"
