from __future__ import annotations

import json

import pytest

from webui.backend.db import get_db


def _login(client):
    client.post("/api/setup", json={"username": "admin", "password": "hunter2hunter2"})
    client.post("/api/login", json={"username": "admin", "password": "hunter2hunter2"})


def _seed_configs(tmp_path, monkeypatch):
    pay_path = tmp_path / "CTF-pay" / "config.paypal.json"
    reg_path = tmp_path / "CTF-reg" / "config.paypal-proxy.json"
    pay_path.parent.mkdir(parents=True, exist_ok=True)
    reg_path.parent.mkdir(parents=True, exist_ok=True)

    pay_path.write_text(json.dumps({
        "paypal": {"email": "payer@example.org", "password": "secret123", "cookies": ""},
        "fresh_checkout": {
            "auth": {
                "session_token": "sess-123",
                "access_token": "at-123",
                "cookie_header": "cookie=1",
                "auto_register": {"config_path": str(reg_path)},
            }
        },
        "cpa": {"enabled": False},
    }), encoding="utf-8")

    reg_path.write_text(json.dumps({
        "mail": {
            "catch_all_domain": "catch.example.org",
            "catch_all_domains": ["catch.example.org"],
        },
        "captcha": {"client_key": "captcha-key"},
    }), encoding="utf-8")

    import webui.backend.settings as s
    monkeypatch.setattr(s, "PAY_CONFIG_PATH", pay_path)
    monkeypatch.setattr(s, "REG_CONFIG_PATH", reg_path)
    return pay_path, reg_path


def test_config_health_fails_without_cloudflare_secrets(client, tmp_path, monkeypatch):
    _login(client)
    _seed_configs(tmp_path, monkeypatch)

    from webui.backend.db import get_db
    get_db().clear_runtime_data()

    r = client.post("/api/config/health", json={"mode": "single", "paypal": True})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    names = {c["name"] for c in body["blocking"]}
    assert "cloudflare_kv_secrets" in names


def test_config_health_ok_with_cloudflare_secrets(client, tmp_path, monkeypatch):
    _login(client)
    _seed_configs(tmp_path, monkeypatch)

    db = get_db()
    db.clear_runtime_data()
    db.set_runtime_json("secrets", {
        "cloudflare": {
            "api_token": "tok-abc",
            "account_id": "acct-123",
            "otp_kv_namespace_id": "kv-123",
        }
    })

    r = client.post("/api/config/health", json={"mode": "single", "paypal": True})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert not body["blocking"]


def test_config_health_session_only_skips_registration_and_payment(client, tmp_path, monkeypatch):
    _login(client)
    _seed_configs(tmp_path, monkeypatch)

    db = get_db()
    db.clear_runtime_data()

    r = client.post("/api/config/health", json={
        "mode": "single",
        "paypal": False,
        "session_only": True,
        "target_emails": ["a@example.com"],
    })
    assert r.status_code == 200
    body = r.json()
    assert body["requires_registration"] is False
    assert body["requires_email_otp"] is True
    assert body["payment_kind"] == "none"
    names = {c["name"] for c in body["checks"]}
    assert "mail_domains" not in names
    payment_check = next(c for c in body["checks"] if c["name"] == "payment_config")
    assert payment_check["status"] == "ok"
    blocking = {c["name"] for c in body["blocking"]}
    assert blocking == {"cloudflare_kv_secrets"}


@pytest.mark.parametrize("register_mode", ["phone_browser", "phone_protocol"])
def test_config_health_phone_register_requires_provider(client, tmp_path, monkeypatch, register_mode):
    _login(client)
    _seed_configs(tmp_path, monkeypatch)

    db = get_db()
    db.clear_runtime_data()
    db.set_runtime_json("secrets", {
        "cloudflare": {
            "api_token": "tok-abc",
            "account_id": "acct-123",
            "otp_kv_namespace_id": "kv-123",
        }
    })

    r = client.post("/api/config/health", json={
        "mode": "single",
        "paypal": True,
        "register_mode": register_mode,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    names = {c["name"] for c in body["blocking"]}
    assert "phone_provider" in names


@pytest.mark.parametrize("register_mode", ["phone_browser", "phone_protocol"])
def test_config_health_phone_register_hero_sms_ok(client, tmp_path, monkeypatch, register_mode):
    _login(client)
    _pay_path, reg_path = _seed_configs(tmp_path, monkeypatch)
    monkeypatch.setenv("HERO_SMS_API_KEY", "secret-token")

    reg = json.loads(reg_path.read_text(encoding="utf-8"))
    reg["phone"] = {
        "enabled": True,
        "provider": "hero_sms",
        "base_url": "https://hero-sms.com/stubs/handler_api.php",
        "api_key_env": "HERO_SMS_API_KEY",
        "service": "tg",
        "country": "2",
    }
    reg_path.write_text(json.dumps(reg), encoding="utf-8")

    db = get_db()
    db.clear_runtime_data()
    db.set_runtime_json("secrets", {
        "cloudflare": {
            "api_token": "tok-abc",
            "account_id": "acct-123",
            "otp_kv_namespace_id": "kv-123",
        }
    })

    r = client.post("/api/config/health", json={
        "mode": "single",
        "paypal": True,
        "register_mode": register_mode,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    phone_check = next(c for c in body["checks"] if c["name"] == "phone_provider")
    assert phone_check["status"] == "ok"
    assert "service=tg" in phone_check["details"]


def test_config_health_portal_protocol_register_only_skips_mail_otp(client, tmp_path, monkeypatch):
    _login(client)
    _seed_configs(tmp_path, monkeypatch)

    db = get_db()
    db.clear_runtime_data()

    r = client.post("/api/config/health", json={
        "mode": "single",
        "paypal": True,
        "register_only": True,
        "register_mode": "portal_protocol",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["requires_email_otp"] is False
    names = {c["name"] for c in body["checks"]}
    assert "portal_protocol" in names
    assert "cloudflare_kv_secrets" in names


def test_config_health_portal_protocol_blocks_payment_chain(client, tmp_path, monkeypatch):
    _login(client)
    _seed_configs(tmp_path, monkeypatch)

    db = get_db()
    db.clear_runtime_data()

    r = client.post("/api/config/health", json={
        "mode": "single",
        "paypal": True,
        "register_mode": "portal_protocol",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    names = {c["name"] for c in body["blocking"]}
    assert "portal_protocol_scope" in names


def test_run_start_blocked_by_config_health(client, tmp_path, monkeypatch):
    _login(client)
    _seed_configs(tmp_path, monkeypatch)

    from webui.backend.db import get_db
    get_db().clear_runtime_data()

    r = client.post("/api/run/start", json={"mode": "single", "paypal": True})
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert "message" in detail
    assert "Cloudflare" in detail["message"] or "cloudflare" in detail["message"].lower()
    assert detail["health"]["blocking"]
