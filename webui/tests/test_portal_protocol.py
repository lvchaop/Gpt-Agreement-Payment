from __future__ import annotations

import base64
import json
import re
import sys
import types
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parents[2]
REG_DIR = ROOT / "CTF-reg"
if str(REG_DIR) not in sys.path:
    sys.path.insert(0, str(REG_DIR))

from config import Config
from portal_identity import generate_password, next_username
from portal_protocol import PortalProtocol, PortalSignupState, detect_outlook_challenge, portal_protocol_register


def test_portal_identity_username_shape_and_password_policy(tmp_path):
    state_path = tmp_path / "portal_state.json"

    name1, seq1 = next_username(state_path, namespace="test-portal", base_dir=tmp_path)
    name2, seq2 = next_username(state_path, namespace="test-portal", base_dir=tmp_path)

    assert seq1 == 1
    assert seq2 == 2
    assert name1 != name2
    assert re.fullmatch(r"[a-z][a-z0-9]{11}", name1)
    assert re.fullmatch(r"[a-z][a-z0-9]{11}", name2)

    password = generate_password(12)
    assert len(password) == 12
    assert any(c.isupper() for c in password)
    assert any(c.islower() for c in password)
    assert any(c.isdigit() for c in password)
    assert any(c in "!@#$%_-" for c in password)


class _FakeResponse:
    def __init__(self, *, url: str, text: str = "", data: dict | None = None, status_code: int = 200):
        self.url = url
        self.text = text
        self._data = data
        self.status_code = status_code
        self.headers = {}

    def json(self):
        if self._data is None:
            raise ValueError("no json")
        return self._data


class _FakeSession:
    def __init__(self, signup_html: str):
        self.headers = {}
        self.signup_html = signup_html
        self.gets: list[str] = []
        self.get_headers: list[tuple[str, dict]] = []
        self.posts: list[tuple[str, dict]] = []
        self.post_headers: list[tuple[str, dict]] = []

    def get(self, url, **kwargs):
        self.gets.append(url)
        self.get_headers.append((url, kwargs.get("headers") or {}))
        if "oauth20_authorize.srf" in url:
            return _FakeResponse(
                url="https://signup.live.com/signup?client_id=cid&uaid=uaid123&mkt=zh-CN&sru=https%3A%2F%2Flogin.live.com%2Foauth20_authorize.srf&uiflavor=host&lw=1&fl=easi2&noauthcancel=1&suc=cid",
                text=self.signup_html,
            )
        if "fpt.live.com/?" in url:
            return _FakeResponse(url=url, text=(
                "<script>var localTarget='https://fpt.live.com/',"
                "txnId='uaid123',ticks='ABC123',rid='rid123',"
                "cid='33e01921-4d64-4f8c-a055-5bdaffd5e33d',"
                "txnKey='session_id',ridKey='id',commonquery='&PageId=SU';</script>"
            ))
        if "fpt.live.com/Images/Clear.PNG" in url:
            return _FakeResponse(url=url, text="")
        return _FakeResponse(url=url, text="")

    def post(self, url, json=None, data=None, **kwargs):
        self.posts.append((url, json or data or {}))
        self.post_headers.append((url, kwargs.get("headers") or {}))
        if "EvaluateExperimentAssignments" in url:
            return _FakeResponse(url=url, data={})
        if "CheckAvailableSigninNames" in url:
            return _FakeResponse(url=url, data={
                "apiCanary": "next-canary",
                "isAvailable": True,
                "nopaAllowed": False,
                "type": "Live",
            })
        if "CreateAccount" in url:
            return _FakeResponse(url=url, data={
                "redirectUrl": "https://login.live.com/oauth20_authorize.srf?client_id=cid&uaid=uaid123",
                "signinName": (json or {}).get("MemberName", ""),
            })
        if "oauth20_authorize.srf" in url:
            return _FakeResponse(url="https://login.live.com/oauth20_desktop.srf?code=abc123&lc=2052")
        return _FakeResponse(url=url, data={})


class _BirthdateRetrySession(_FakeSession):
    def __init__(self, signup_html: str):
        super().__init__(signup_html)
        self.create_calls = 0

    def post(self, url, json=None, data=None, **kwargs):
        if "CreateAccount" not in url:
            return super().post(url, json=json, data=data, **kwargs)
        self.create_calls += 1
        self.posts.append((url, json or data or {}))
        self.post_headers.append((url, kwargs.get("headers") or {}))
        if self.create_calls == 1:
            return _FakeResponse(url=url, data={
                "error": {
                    "code": "1039",
                    "field": "birthdate",
                    "data": "",
                    "telemetryContext": "retry-test",
                }
            })
        return _FakeResponse(url=url, data={
            "redirectUrl": "https://login.live.com/oauth20_authorize.srf?client_id=cid&uaid=uaid123",
            "signinName": (json or {}).get("MemberName", ""),
        })


def test_portal_protocol_uses_hmac_identity_and_live_api_shape(tmp_path):
    server_data = {
        "apiCanary": "initial-canary",
        "sUnauthSessionID": "uaid123",
        "sClientId": "cid",
        "sMkt": "zh-CN",
        "hpgid": 200225,
        "iUiFlavor": 1,
        "iScenarioId": 100118,
        "urlCheckAvailableSigninNames": "https://signup.live.com/API/CheckAvailableSigninNames",
        "urlCreateAccount": "https://signup.live.com/API/CreateAccount",
        "urlClientExperiment": "https://signup.live.com/API/EvaluateExperimentAssignments",
        "oCaptchaInfo": {
            "urlDfp": "https://fpt.live.com/?session_id=uaid123&CustomerId=33e01921-4d64-4f8c-a055-5bdaffd5e33d&PageId=SU",
        },
    }
    signup_html = f"<html><script>var ServerData = {json.dumps(server_data)};</script></html>"
    session = _FakeSession(signup_html)

    cfg = Config()
    cfg.portal_protocol.state_path = str(tmp_path / "identity.json")
    cfg.portal_protocol.namespace = "test-portal"
    cfg.portal_protocol.account_domain = "outlook.com"
    cfg.portal_protocol.mail_oauth_enabled = False

    result = PortalProtocol(cfg, session=session).run().to_dict()

    assert result["register_method"] == "portal_protocol"
    assert re.fullmatch(r"[a-z][a-z0-9]{11}@outlook\.com", result["email"])
    assert result["email"] == result["email"].lower()
    assert result["portal_oauth_code_captured"] is True
    create_payload = next(payload for url, payload in session.posts if "CreateAccount" in url)
    assert create_payload["MemberName"] == result["email"]
    assert create_payload["Password"] == result["password"]
    assert create_payload["uaid"] == "uaid123"
    assert any("fpt.live.com/?session_id=uaid123" in url for url in session.gets)
    assert any("fpt.live.com/Images/Clear.PNG" in url for url in session.gets)
    create_headers = next(headers for url, headers in session.post_headers if "CreateAccount" in url)
    assert create_headers["client-request-id"] == "uaid123"
    assert create_headers["correlationId"] == "uaid123"
    authorize_url = next(url for url in session.gets if "oauth20_authorize.srf" in url)
    authorize_qs = parse_qs(urlparse(authorize_url).query)
    assert authorize_qs["client_id"] == ["00000000480728C5"]

    fpt_headers = next(headers for url, headers in session.get_headers if "fpt.live.com/?session_id=uaid123" in url)
    assert fpt_headers["Sec-Fetch-Site"] == "same-site"
    clear_url = next(url for url in session.gets if "fpt.live.com/Images/Clear.PNG" in url)
    clear_qs = parse_qs(urlparse(clear_url).query)
    esi = base64.b64decode(clear_qs["esi"][0]).decode("utf-8")
    eci = base64.b64decode(clear_qs["eci"][0]).decode("utf-8")
    assert "mth=27f51d3149e6bf209b66bd387b0af3c4" in esi
    assert "plugin_flash%3Dfalse" in esi
    assert "fh=07d7339f27cd6608358c55b7fda0f9ec" in esi
    assert "c=bdef6bc2985d5a701a6bf7d693ef085b" in esi
    assert '"vdr":"WebKit"' in eci


def test_portal_protocol_mail_oauth_uses_separate_client_id(tmp_path, monkeypatch):
    server_data = {
        "apiCanary": "initial-canary",
        "sUnauthSessionID": "uaid123",
        "sClientId": "cid",
        "sMkt": "zh-CN",
        "hpgid": 200225,
        "iUiFlavor": 1,
        "iScenarioId": 100118,
        "urlCheckAvailableSigninNames": "https://signup.live.com/API/CheckAvailableSigninNames",
        "urlCreateAccount": "https://signup.live.com/API/CreateAccount",
        "urlClientExperiment": "https://signup.live.com/API/EvaluateExperimentAssignments",
    }
    signup_html = f"<html><script>var ServerData = {json.dumps(server_data)};</script></html>"
    session = _FakeSession(signup_html)
    captured = {}

    class FakeOAuth:
        client_id = "d8bd9ced-3bad-4ecf-86f2-090009874b3e"

        def to_mail_fields(self):
            return {
                "mail_account_id": self.client_id,
                "mail_access_token": "mail-at",
                "mail_refresh_token": "mail-rt",
                "mail_oauth_scope": "offline_access test.scope",
            }

    def fake_authorize(cfg, used_session, *, email, password):
        captured["client_id"] = cfg.portal_protocol.client_id
        captured["mail_oauth_client_id"] = cfg.portal_protocol.mail_oauth_client_id
        captured["same_session"] = used_session is session
        captured["email"] = email
        captured["password"] = password
        return FakeOAuth()

    fake_mod = types.ModuleType("outlook_oauth")
    fake_mod.authorize_outlook_mailbox = fake_authorize
    monkeypatch.setitem(sys.modules, "outlook_oauth", fake_mod)

    cfg = Config()
    cfg.portal_protocol.state_path = str(tmp_path / "identity.json")
    cfg.portal_protocol.namespace = "test-portal"
    cfg.portal_protocol.account_domain = "outlook.com"

    result = PortalProtocol(cfg, session=session).run().to_dict()

    assert captured["client_id"] == "00000000480728C5"
    assert captured["mail_oauth_client_id"] == "d8bd9ced-3bad-4ecf-86f2-090009874b3e"
    assert captured["same_session"] is True
    assert captured["email"] == result["email"]
    assert captured["password"] == result["password"]
    assert result["mail_account_id"] == "d8bd9ced-3bad-4ecf-86f2-090009874b3e"
    assert result["mail_refresh_token"] == "mail-rt"


def test_portal_protocol_retries_birthdate_error_with_same_account(tmp_path):
    server_data = {
        "apiCanary": "initial-canary",
        "sUnauthSessionID": "uaid123",
        "sClientId": "cid",
        "sMkt": "zh-CN",
        "hpgid": 200225,
        "iUiFlavor": 1,
        "iScenarioId": 100118,
        "sDateOrder": "YMD",
        "urlCheckAvailableSigninNames": "https://signup.live.com/API/CheckAvailableSigninNames",
        "urlCreateAccount": "https://signup.live.com/API/CreateAccount",
        "urlClientExperiment": "https://signup.live.com/API/EvaluateExperimentAssignments",
    }
    signup_html = f"<html><script>var ServerData = {json.dumps(server_data)};</script></html>"
    session = _BirthdateRetrySession(signup_html)

    cfg = Config()
    cfg.portal_protocol.state_path = str(tmp_path / "identity.json")
    cfg.portal_protocol.namespace = "test-portal"
    cfg.portal_protocol.account_domain = "outlook.com"
    cfg.portal_protocol.country = "JP"
    cfg.portal_protocol.mail_oauth_enabled = False

    result = PortalProtocol(cfg, session=session).run().to_dict()

    create_payloads = [payload for url, payload in session.posts if "CreateAccount" in url]
    assert result["register_method"] == "portal_protocol"
    assert len(create_payloads) == 2
    assert create_payloads[0]["MemberName"] == create_payloads[1]["MemberName"]
    assert create_payloads[0]["Password"] == create_payloads[1]["Password"]
    assert re.fullmatch(r"\d{2}:\d{2}:\d{4}", create_payloads[0]["BirthDate"])
    assert create_payloads[0]["BirthDate"] != create_payloads[1]["BirthDate"]


def _portal_state_with_order(order: str = "") -> PortalSignupState:
    return PortalSignupState(
        signup_url="https://signup.live.com/signup",
        api_canary="canary",
        uaid="uaid123",
        client_id="cid",
        mkt="zh-CN",
        hpgid=200225,
        scid=100118,
        uiflvr=1,
        check_url="https://signup.live.com/API/CheckAvailableSigninNames",
        create_url="https://signup.live.com/API/CreateAccount",
        server_data={"sDateOrder": order} if order else {},
    )


def test_portal_birth_date_formats_by_country_not_server_display_order():
    cfg = Config()
    portal = PortalProtocol(cfg, session=_FakeSession("<html></html>"))

    ymd, ymd_order, ymd_source, ymd_days = portal._birth_date(_portal_state_with_order("YMD"), "JP")
    assert re.fullmatch(r"\d{2}:\d{2}:\d{4}", ymd)
    assert ymd_order == "DMY"
    assert ymd_source == "country:JP"
    assert 20 * 365 <= ymd_days <= 40 * 366

    dmy, dmy_order, dmy_source, _ = portal._birth_date(_portal_state_with_order(), "GB")
    assert re.fullmatch(r"\d{2}:\d{2}:\d{4}", dmy)
    assert dmy_order == "DMY"
    assert dmy_source == "country:GB"

    mdy, mdy_order, mdy_source, _ = portal._birth_date(_portal_state_with_order(), "US")
    assert re.fullmatch(r"\d{2}:\d{2}:\d{4}", mdy)
    assert mdy_order == "MDY"
    assert mdy_source == "country:US"


def test_detect_outlook_challenge_markers():
    px_resp = _FakeResponse(url="https://signup.live.com/", text='<div id="px-captcha">Press and hold</div>')
    assert detect_outlook_challenge(px_resp) == ("perimeterx", "px-captcha")

    reason, marker = detect_outlook_challenge(data={"error": {"field": "hipChallenge", "data": "GetHIP"}})
    assert reason == "microsoft_hip"
    assert marker in {"hipchallenge", "gethip"}

    reason, marker = detect_outlook_challenge(data={"error": {"field": "humanCaptcha", "code": "1059"}})
    assert reason == "generic_challenge"
    assert marker == "humancaptcha"


def test_portal_authorize_ignores_har_hsprotect_weak_marker():
    cfg = Config()
    portal = PortalProtocol(cfg, session=_FakeSession("<html></html>"))
    resp = _FakeResponse(url="https://signup.live.com/signup", text="<script src='https://hsprotect.net/foo.js'></script>")

    portal._raise_if_challenge(resp, stage="authorize/signup")


def test_portal_protocol_challenge_falls_back_to_outlook_browser(tmp_path, monkeypatch):
    server_data = {
        "apiCanary": "initial-canary",
        "sUnauthSessionID": "uaid123",
        "sClientId": "cid",
        "sMkt": "zh-CN",
        "hpgid": 200225,
        "iUiFlavor": 1,
        "iScenarioId": 100118,
        "urlCheckAvailableSigninNames": "https://signup.live.com/API/CheckAvailableSigninNames",
        "urlCreateAccount": "https://signup.live.com/API/CreateAccount",
        "urlClientExperiment": "https://signup.live.com/API/EvaluateExperimentAssignments",
    }
    signup_html = f"<html><script>var ServerData = {json.dumps(server_data)};</script></html>"

    class ChallengeSession(_FakeSession):
        def post(self, url, json=None, data=None, **kwargs):
            if "CheckAvailableSigninNames" in url:
                return _FakeResponse(url=url, data={
                    "error": {
                        "field": "hipChallenge",
                        "data": "GetHIP",
                    }
                })
            return super().post(url, json=json, data=data, **kwargs)

    captured = {}

    def fake_browser_register(cfg, *, email="", password="", username_seq=0, challenge_reason=""):
        captured.update({
            "email": email,
            "password": password,
            "username_seq": username_seq,
            "challenge_reason": challenge_reason,
        })
        return {
            "email": email,
            "password": password,
            "register_method": "portal_browser",
        }

    fake_mod = types.ModuleType("outlook_browser_register")
    fake_mod.outlook_browser_register = fake_browser_register
    monkeypatch.setitem(sys.modules, "outlook_browser_register", fake_mod)

    cfg = Config()
    cfg.portal_protocol.state_path = str(tmp_path / "identity.json")
    cfg.portal_protocol.namespace = "test-portal"
    cfg.portal_protocol.account_domain = "outlook.com"
    cfg.portal_protocol.mail_oauth_enabled = False

    result = portal_protocol_register(cfg, session=ChallengeSession(signup_html))

    assert result["register_method"] == "portal_browser"
    assert result["email"].endswith("@outlook.com")
    assert captured["email"] == result["email"]
    assert captured["password"] == result["password"]
    assert captured["username_seq"] == 1
    assert captured["challenge_reason"] == "microsoft_hip"
