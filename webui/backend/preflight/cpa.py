import httpx
from pydantic import BaseModel
from ._common import CheckResult, PreflightResult, aggregate


class CPAInput(BaseModel):
    base_url: str
    admin_key: str
    target: str = "cpa"


def _sub2api_accounts_url(base: str) -> str:
    if base.endswith("/api/v1"):
        return f"{base}/admin/accounts"
    if base.endswith("/api"):
        return f"{base}/v1/admin/accounts"
    return f"{base}/api/v1/admin/accounts"


def _auth_header_value(token: str) -> str:
    token = token.strip()
    if token.lower().startswith("bearer "):
        return token
    return f"Bearer {token}"


def check(body: dict) -> PreflightResult:
    cfg = CPAInput.model_validate(body)
    base = cfg.base_url.rstrip("/")
    headers = {"Authorization": _auth_header_value(cfg.admin_key)}
    target = (cfg.target or "cpa").strip().lower()
    try:
        with httpx.Client(timeout=15.0) as c:
            if target == "sub2api":
                r = c.get(_sub2api_accounts_url(base), headers=headers)
            else:
                r = c.get(f"{base}/v0/management/auth-files", headers=headers)
    except httpx.HTTPError as e:
        return aggregate([CheckResult(name="management", status="fail",
                                      message=str(e))])
    if r.status_code == 200:
        try:
            data = r.json()
            if isinstance(data, dict) and isinstance(data.get("data"), dict):
                payload = data["data"]
            else:
                payload = data
            n = len(payload) if isinstance(payload, list) else (
                payload.get("total") or payload.get("count") if isinstance(payload, dict) else "?")
        except Exception:
            n = "?"
        if target == "sub2api":
            return aggregate([CheckResult(name="management", status="ok",
                                          message=f"sub2api accounts reachable ({n} entries)")])
        return aggregate([CheckResult(name="management", status="ok",
                                      message=f"auth-files reachable ({n} entries)")])
    if r.status_code in (401, 403):
        return aggregate([CheckResult(name="management", status="fail",
                                      message=f"HTTP {r.status_code} — admin_key 无效或被拒",
                                      details=(r.text[:500] +
                                               "\n⚠ 该服务对错误 key 会限频/封 IP，请勿连续重试"))])
    return aggregate([CheckResult(name="management", status="fail",
                                  message=f"HTTP {r.status_code}",
                                  details=r.text[:1000])])
