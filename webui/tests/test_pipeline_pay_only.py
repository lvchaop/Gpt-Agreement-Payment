import json
import sys
import threading
import time
import types

import pipeline
from webui.backend.db import get_db


def _reset_db(tmp_path, monkeypatch):
    monkeypatch.setenv("WEBUI_DATA_DIR", str(tmp_path))
    db = get_db()
    db.clear_runtime_data()
    return db


def test_pay_only_selects_latest_registered_unpaid_account(tmp_path, monkeypatch):
    db = _reset_db(tmp_path, monkeypatch)

    for row in [
        {
            "ts": "2026-05-03T01:00:00+00:00",
            "email": "paid@example.com",
            "session_token": "sess-paid",
            "access_token": "at-paid",
            "device_id": "dev-paid",
        },
        {
            "ts": "2026-05-03T02:00:00+00:00",
            "email": "retry@example.com",
            "session_token": "sess-retry",
            "access_token": "at-retry",
            "device_id": "dev-retry",
        },
        {
            "ts": "2026-05-03T03:00:00+00:00",
            "email": "no-auth@example.com",
            "session_token": "",
            "access_token": "",
            "device_id": "dev-noauth",
        },
    ]:
        db.add_registered_account(row)
    db.add_pipeline_result({
        "registration": {"status": "ok", "email": "paid@example.com"},
        "payment": {"status": "succeeded", "email": "paid@example.com"},
    })
    db.add_pipeline_result({
        "registration": {"status": "ok", "email": "retry@example.com"},
        "payment": {"status": "error", "email": "retry@example.com", "error": "OTP timeout"},
    })

    selected = pipeline._select_recent_registered_account_for_pay_only()
    assert selected is not None
    assert selected["email"] == "retry@example.com"
    assert selected["session_token"] == "sess-retry"
    assert selected["access_token"] == "at-retry"


def test_register_only_batch_uses_workers(tmp_path, monkeypatch):
    cardw_config = tmp_path / "reg.json"
    cardw_config.write_text("{}", encoding="utf-8")
    card_config = tmp_path / "pay.json"
    card_config.write_text(json.dumps({
        "fresh_checkout": {
            "auth": {
                "auto_register": {"config_path": str(cardw_config)},
            },
        },
    }), encoding="utf-8")

    lock = threading.Lock()
    active = 0
    peak = 0
    methods: list[str | None] = []

    def fake_register(*args, **kwargs):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
            methods.append(kwargs.get("register_method"))
            idx = len(methods)
        time.sleep(0.05)
        with lock:
            active -= 1
        return {"email": f"user{idx}@example.test"}

    monkeypatch.setattr(pipeline, "register", fake_register)

    results = pipeline.batch(
        str(card_config),
        3,
        delay=0,
        workers=3,
        register_only=True,
        register_method="phone_protocol",
    )

    assert len(results) == 3
    assert all(r["status"] == "ok" for r in results)
    assert all(m == "phone_protocol" for m in methods)
    assert peak > 1


def test_paypal_new_user_batch_rewrite_defers_phone_index(tmp_path):
    phones = tmp_path / "phones.jsonl"
    phones.write_text('{"phone":"+817012345678","country":"JP","activation_id":"a1"}\n', encoding="utf-8")
    cfg_path = tmp_path / "pay.json"
    cfg_path.write_text(json.dumps({
        "paypal": {
            "flow": "new_user",
            "phones_file": str(phones),
            "phone_index": 0,
            "manual_otp_file": "output/paypal_new_user_otp.txt",
        },
    }), encoding="utf-8")

    lease_dir = tmp_path / "leases"
    temp_path = pipeline._rewrite_paypal_new_user_batch_config(
        str(cfg_path),
        4,
        phone_lease_dir=str(lease_dir),
    )

    try:
        rewritten = json.loads(open(temp_path, encoding="utf-8").read())
    finally:
        try:
            import os
            os.unlink(temp_path)
        except Exception:
            pass

    paypal = rewritten["paypal"]
    assert "phone_index" not in paypal
    assert paypal["_batch_phone_lease_dir"] == str(lease_dir)
    assert paypal["_batch_index"] == 4


def test_pay_only_treats_already_paid_error_as_consumed(tmp_path, monkeypatch):
    db = _reset_db(tmp_path, monkeypatch)

    db.add_registered_account({"email": "older@example.com", "session_token": "sess-older", "access_token": ""})
    db.add_registered_account({"email": "latest@example.com", "session_token": "sess-latest", "access_token": ""})
    db.add_pipeline_result({
        "registration": {"status": "ok", "email": "latest@example.com"},
        "payment": {
            "status": "error",
            "email": "latest@example.com",
            "error": '生成 fresh checkout 失败: modern [400]: {"detail":"User is already paid"}',
        },
    })

    selected = pipeline._select_recent_registered_account_for_pay_only()
    assert selected is not None
    assert selected["email"] == "older@example.com"


def test_pay_only_skips_accounts_already_verified_as_paid_plan(tmp_path, monkeypatch):
    db = _reset_db(tmp_path, monkeypatch)

    for email, plan in [
        ("free@example.com", "free"),
        ("plus@example.com", "plus"),
        ("team@example.com", "team"),
    ]:
        db.add_registered_account({
            "email": email,
            "session_token": f"sess-{plan}",
            "access_token": f"at-{plan}",
        })
        row = next(row for row in db.iter_registered_accounts() if row["email"] == email)
        db.update_account_check(row["id"], "valid", plan_type=plan)

    selected = pipeline._select_recent_registered_accounts_for_pay_only(3)

    assert [row["email"] for row in selected] == ["free@example.com"]


def test_pay_only_success_imports_cpa_with_plus_tag(tmp_path, monkeypatch):
    db = _reset_db(tmp_path, monkeypatch)
    card_config = tmp_path / "config.paypal.json"

    db.add_registered_account({
        "email": "retry@example.com",
        "session_token": "sess-retry",
        "access_token": "at-retry",
        "device_id": "dev-retry",
    })
    card_config.write_text(json.dumps({
        "fresh_checkout": {"plan": {"plan_name": "chatgptplusplan"}},
        "cpa": {
            "enabled": True,
            "base_url": "https://cpa.example.com",
            "admin_key": "adm",
            "oauth_client_id": "app_test",
            "plan_tag": "team",
        },
    }), encoding="utf-8")

    calls = []

    def fake_pay(*args, **kwargs):
        return {
            "status": "succeeded",
            "raw": {
                "session_id": "cs_test",
                "chatgpt_email": "retry@example.com",
            },
        }

    def fake_cpa(email, sid, cpa_cfg, **kwargs):
        calls.append((email, sid, cpa_cfg, kwargs))
        return "ok"

    monkeypatch.setattr(pipeline, "pay", fake_pay)
    monkeypatch.setattr(pipeline, "_cpa_import_after_team", fake_cpa)

    result = pipeline.pay_only(str(card_config), use_gopay=True)

    assert result["status"] == "succeeded"
    assert calls
    email, sid, cpa_cfg, kwargs = calls[0]
    assert email == "retry@example.com"
    assert sid == "cs_test"
    assert cpa_cfg["plan_tag"] == "plus"
    rows = get_db().iter_pipeline_results()
    assert rows[-1]["cpa_import"] == "ok"


def test_cpa_import_falls_back_to_access_token_without_refresh_token(tmp_path, monkeypatch):
    db = _reset_db(tmp_path, monkeypatch)
    db.add_registered_account({
        "email": "fallback@example.com",
        "access_token": "eyJhbGciOiJub25lIn0.eyJodHRwczovL2FwaS5vcGVuYWkuY29tL2F1dGgiOnsiY2hhdGdwdF9hY2NvdW50X2lkIjoiYWNjdF8xMjMifSwiZXhwIjoyNTM0MDk0NDAwfQ.sig",
    })
    monkeypatch.setattr(pipeline, "_find_latest_refresh_token_for_email", lambda *args, **kwargs: "")

    fake_calls = []

    class FakeResponse:
        status_code = 200
        text = ""

    class FakeSession:
        def __init__(self, *args, **kwargs):
            self.proxies = {}
            self.trust_env = False

        def post(self, url, params=None, json=None, headers=None, timeout=None):
            fake_calls.append({"url": url, "params": params, "json": json, "headers": headers, "timeout": timeout})
            return FakeResponse()

    fake_requests = types.ModuleType("curl_cffi.requests")
    fake_requests.Session = lambda impersonate=None: FakeSession()
    fake_pkg = types.ModuleType("curl_cffi")
    fake_pkg.requests = fake_requests
    monkeypatch.setitem(sys.modules, "curl_cffi", fake_pkg)
    monkeypatch.setitem(sys.modules, "curl_cffi.requests", fake_requests)

    status = pipeline._cpa_import_after_team(
        "fallback@example.com",
        "cs_test",
        {
            "enabled": True,
            "base_url": "https://cpa.example.com",
            "admin_key": "secret-admin-key",
            "oauth_client_id": "app_test_client",
            "plan_tag": "team",
            "free_plan_tag": "free",
        },
    )

    assert status == "ok"
    assert fake_calls
    body = fake_calls[0]["json"]
    assert body["email"] == "fallback@example.com"
    assert body["access_token"].startswith("eyJhbGciOiJub25lIn0.")
    assert body["refresh_token"] == ""
    assert body["account_id"] == "acct_123"
