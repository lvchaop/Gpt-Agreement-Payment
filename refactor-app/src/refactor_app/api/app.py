from __future__ import annotations

import hashlib
import hmac
from html import escape
from urllib.parse import parse_qs, quote

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from refactor_app.api.routes.health import router as health_router
from refactor_app.api.routes.jobs import router as jobs_router
from refactor_app.api.routes.ops import router as ops_router
from refactor_app.api.routes.resources import router as resources_router
from refactor_app.api.routes.resources import start_automation_scheduler
from refactor_app.config.settings import get_settings


WEB_SESSION_COOKIE = "refactor_app_web_session"
WEB_SESSION_SALT = b"refactor-app-web-login"


def create_app() -> FastAPI:
    app = FastAPI(title="refactor-app")

    @app.middleware("http")
    async def _require_web_login(request: Request, call_next) -> Response:
        password = _web_login_password()
        path = request.url.path
        if not password or _is_public_path(path) or _has_valid_web_session(request, password):
            return await call_next(request)
        if _wants_html(request):
            next_path = _current_path_with_query(request)
            return RedirectResponse(f"/login?next={quote(next_path, safe='')}", status_code=303)
        return JSONResponse({"detail": "web login required"}, status_code=401)

    @app.get("/login", response_class=HTMLResponse)
    async def _login_page(request: Request) -> Response:
        if not _web_login_password():
            return RedirectResponse(_safe_next(request.query_params.get("next") or "/ops"), status_code=303)
        return HTMLResponse(_login_html(next_value=request.query_params.get("next") or "/ops"))

    @app.post("/login", response_class=HTMLResponse)
    async def _login_submit(request: Request) -> Response:
        password = _web_login_password()
        if not password:
            return RedirectResponse("/ops", status_code=303)
        form = parse_qs((await request.body()).decode("utf-8", errors="replace"))
        submitted = form.get("password", [""])[0]
        next_value = _safe_next(form.get("next", ["/ops"])[0])
        if not hmac.compare_digest(submitted, password):
            return HTMLResponse(_login_html(next_value=next_value, error="密码错误"), status_code=401)
        response = RedirectResponse(next_value, status_code=303)
        response.set_cookie(
            WEB_SESSION_COOKIE,
            _web_session_token(password),
            httponly=True,
            samesite="lax",
            secure=False,
            path="/",
        )
        return response

    @app.get("/logout")
    async def _logout() -> Response:
        response = RedirectResponse("/login", status_code=303)
        response.delete_cookie(WEB_SESSION_COOKIE, path="/")
        return response

    app.include_router(health_router)
    app.include_router(jobs_router)
    app.include_router(resources_router)
    app.include_router(ops_router)

    @app.on_event("startup")
    def _start_automation_scheduler() -> None:
        start_automation_scheduler()

    return app


def _web_login_password() -> str:
    return get_settings().web_login_password.strip()


def _web_session_token(password: str) -> str:
    return hmac.new(password.encode("utf-8"), WEB_SESSION_SALT, hashlib.sha256).hexdigest()


def _has_valid_web_session(request: Request, password: str) -> bool:
    value = request.cookies.get(WEB_SESSION_COOKIE, "")
    return bool(value) and hmac.compare_digest(value, _web_session_token(password))


def _is_public_path(path: str) -> bool:
    return path in {"/health", "/login", "/logout", "/favicon.ico"} or path.startswith("/login?")


def _wants_html(request: Request) -> bool:
    accept = request.headers.get("accept", "")
    return request.url.path.startswith("/ops") or "text/html" in accept


def _current_path_with_query(request: Request) -> str:
    path = request.url.path
    if request.url.query:
        return f"{path}?{request.url.query}"
    return path


def _safe_next(value: str) -> str:
    if not value.startswith("/") or value.startswith("//"):
        return "/ops"
    return value


def _login_html(next_value: str, error: str = "") -> str:
    safe_next = escape(_safe_next(next_value), quote=True)
    error_html = f'<div class="error">{escape(error)}</div>' if error else ""
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>登录 - Refactor App</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #070b16;
      --panel: #111827;
      --line: #273449;
      --text: #e5e7eb;
      --muted: #94a3b8;
      --blue: #3b82f6;
      --red: #fca5a5;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      background: radial-gradient(circle at top, #18213a 0, var(--bg) 52%);
      color: var(--text);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    main {{
      width: min(420px, calc(100vw - 32px));
      padding: 28px;
      border: 1px solid var(--line);
      border-radius: 18px;
      background: rgba(17, 24, 39, 0.92);
      box-shadow: 0 24px 80px rgba(0, 0, 0, 0.38);
    }}
    h1 {{ margin: 0 0 8px; font-size: 24px; }}
    p {{ margin: 0 0 24px; color: var(--muted); }}
    label {{ display: block; margin-bottom: 8px; color: var(--muted); font-weight: 700; }}
    input {{
      width: 100%;
      height: 48px;
      padding: 0 14px;
      border: 1px solid var(--line);
      border-radius: 12px;
      background: #0b1220;
      color: var(--text);
      font-size: 16px;
      outline: none;
    }}
    input:focus {{ border-color: var(--blue); box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.25); }}
    button {{
      width: 100%;
      height: 46px;
      margin-top: 18px;
      border: 0;
      border-radius: 12px;
      background: var(--blue);
      color: white;
      font-size: 16px;
      font-weight: 800;
      cursor: pointer;
    }}
    .error {{
      margin-bottom: 14px;
      padding: 10px 12px;
      border: 1px solid rgba(248, 113, 113, 0.45);
      border-radius: 10px;
      color: var(--red);
      background: rgba(127, 29, 29, 0.28);
    }}
  </style>
</head>
<body>
  <main>
    <h1>Web 控制台登录</h1>
    <p>输入环境变量 REFACTOR_APP_WEB_LOGIN_PASSWORD 配置的密码。</p>
    {error_html}
    <form method="post" action="/login">
      <input type="hidden" name="next" value="{safe_next}" />
      <label for="password">密码</label>
      <input id="password" name="password" type="password" autocomplete="current-password" autofocus />
      <button type="submit">登录</button>
    </form>
  </main>
</body>
</html>"""
