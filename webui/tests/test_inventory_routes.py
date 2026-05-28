from __future__ import annotations

from datetime import datetime, timedelta, timezone

from webui.backend.db import get_db


def _login(client):
    client.post("/api/setup", json={"username": "admin", "password": "hunter2hunter2"})
    client.post("/api/login", json={"username": "admin", "password": "hunter2hunter2"})


def test_inventory_requires_auth(client):
    r = client.get("/api/inventory/accounts")
    assert r.status_code == 401


def test_inventory_summarizes_pay_and_rt_states(client):
    _login(client)
    db = get_db()
    db.clear_runtime_data()

    now = datetime.now(timezone.utc)
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
            "email": "noauth@example.com",
            "session_token": "",
            "access_token": "",
            "device_id": "dev-noauth",
        },
        {
            "ts": "2026-05-03T04:00:00+00:00",
            "email": "hasrt@example.com",
            "session_token": "sess-rt",
            "access_token": "at-rt",
            "device_id": "dev-rt",
            "refresh_token": "rt-hasrt",
        },
        {
            "ts": "2026-05-03T05:00:00+00:00",
            "email": "dead@example.com",
            "session_token": "sess-dead",
            "access_token": "at-dead",
            "device_id": "dev-dead",
        },
    ]:
        db.add_registered_account(row)

    db.add_pipeline_result({
        "ts": "2026-05-03T10:00:00+00:00",
        "registration": {"status": "ok", "email": "paid@example.com"},
        "payment": {"status": "succeeded", "email": "paid@example.com"},
    })
    db.add_pipeline_result({
        "ts": "2026-05-03T11:00:00+00:00",
        "registration": {"status": "ok", "email": "retry@example.com"},
        "payment": {"status": "error", "email": "retry@example.com", "error": "OTP timeout"},
    })
    db.set_oauth_status(
        "retry@example.com",
        "transient_failed",
        "otp_timeout",
        (now - timedelta(minutes=10)).isoformat(),
    )
    db.set_oauth_status(
        "dead@example.com",
        "dead",
        "account_dead",
        now.isoformat(),
    )

    r = client.get("/api/inventory/accounts")
    assert r.status_code == 200
    body = r.json()

    assert body["counts"]["registered_total"] == 5
    assert body["counts"]["raw_registered_rows"] == 5
    assert body["counts"]["with_auth"] == 4
    assert body["counts"]["pay_only_eligible"] == 3
    assert body["counts"]["pay_only_consumed"] == 1
    assert body["counts"]["pay_only_no_auth"] == 1
    assert body["counts"]["with_refresh_token"] == 1
    assert body["counts"]["rt_missing"] == 2
    assert body["counts"]["rt_processed"] == 1
    assert body["counts"]["rt_cooldown"] == 1
    assert body["counts"]["rt_dead"] == 1

    by_email = {acc["email"]: acc for acc in body["accounts"]}
    assert by_email["paid@example.com"]["pay_state"] == "consumed"
    assert by_email["paid@example.com"]["sale_status"] == "available"
    assert by_email["paid@example.com"]["sold_at"] == 0
    assert by_email["paid@example.com"]["sale_note"] == ""
    assert by_email["retry@example.com"]["pay_state"] == "reusable"
    assert by_email["retry@example.com"]["rt_state"] == "cooldown"
    assert by_email["retry@example.com"]["can_backfill_rt"] is False
    assert by_email["noauth@example.com"]["pay_state"] == "no_auth"
    assert by_email["hasrt@example.com"]["rt_state"] == "has_rt"
    assert by_email["dead@example.com"]["rt_state"] == "dead"
    # 新字段：每个 item 都暴露 id 和 last_check_*
    for acc in body["accounts"]:
        assert "id" in acc and isinstance(acc["id"], int)
        assert acc["last_check_status"] == ""
        assert acc["last_check_at"] == 0
        assert acc["last_plan_type"] == ""


def test_inventory_uses_verified_plan_as_consumed(client):
    _login(client)
    db = get_db()
    db.clear_runtime_data()
    db.add_registered_account({
        "ts": "2026-05-03T01:00:00+00:00",
        "email": "verified-plus@example.com",
        "session_token": "sess-plus",
        "access_token": "at-plus",
    })
    account_id = db.iter_registered_accounts()[0]["id"]
    db.update_account_check(account_id, "valid", "check/v4 ok", plan_type="plus")

    r = client.get("/api/inventory/accounts")
    assert r.status_code == 200
    account = r.json()["accounts"][0]
    assert account["plan_tag"] == "plus"
    assert account["last_plan_type"] == "plus"
    assert account["pay_state"] == "consumed"
    assert account["plan_source"] == "rt"


def test_delete_requires_auth(client):
    r = client.post("/api/inventory/accounts/delete", json={"ids": [1]})
    assert r.status_code == 401


def test_sale_claim_requires_auth(client):
    r = client.post("/api/inventory/accounts/sale/claim", json={})
    assert r.status_code == 401


def test_sale_claim_returns_password_and_marks_sold(client):
    _login(client)
    db = get_db()
    db.clear_runtime_data()
    db.add_registered_account({"email": "empty-plus@example.com", "password": ""})
    db.add_card_result({"chatgpt_email": "empty-plus@example.com", "status": "succeeded"})
    db.add_registered_account({"email": "free@example.com", "password": "free-pass"})
    db.add_registered_account({"email": "sell@example.com", "password": "secret-pass"})
    db.upsert_mail_accounts([{"email": "sell@example.com", "mail_password": "mail-secret"}])
    db.add_card_result({"chatgpt_email": "sell@example.com", "status": "succeeded"})

    r = client.post("/api/inventory/accounts/sale/claim", json={"note": "order-42"})

    assert r.status_code == 200
    body = r.json()
    assert body["email"] == "sell@example.com"
    assert body["password"] == "secret-pass"
    assert body["gpt_password"] == "secret-pass"
    assert body["mail_password"] == "mail-secret"
    assert body["sale_status"] == "sold"
    assert body["sold_at"] > 0
    assert body["sale_note"] == "order-42"

    by_email = {row["email"]: row for row in db.iter_registered_accounts()}
    assert by_email["empty-plus@example.com"]["sale_status"] == "available"
    assert by_email["free@example.com"]["sale_status"] == "available"
    assert by_email["sell@example.com"]["sale_status"] == "sold"
    assert by_email["sell@example.com"]["sale_note"] == "order-42"

    r2 = client.post("/api/inventory/accounts/sale/claim", json={"note": "order-43"})
    assert r2.status_code == 404


def test_sale_toggle_switches_status(client):
    _login(client)
    db = get_db()
    db.clear_runtime_data()
    db.add_registered_account({"email": "toggle@example.com", "password": "secret-pass"})
    account_id = db.iter_registered_accounts()[0]["id"]

    r = client.post("/api/inventory/accounts/sale/toggle", json={"id": account_id, "note": "sold-note"})
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == "toggle@example.com"
    assert body["sale_status"] == "sold"
    assert body["sold_at"] > 0
    assert body["sale_note"] == "sold-note"

    r2 = client.post("/api/inventory/accounts/sale/toggle", json={"id": account_id})
    assert r2.status_code == 200
    body2 = r2.json()
    assert body2["sale_status"] == "available"
    assert body2["sold_at"] == 0
    assert body2["sale_note"] == ""

    r3 = client.post("/api/inventory/accounts/sale/toggle", json={"id": 999999})
    assert r3.status_code == 404


def test_delete_rejects_empty_ids(client):
    _login(client)
    r = client.post("/api/inventory/accounts/delete", json={"ids": []})
    assert r.status_code == 400


def test_delete_hard_deletes_accounts(client):
    _login(client)
    db = get_db()
    db.clear_runtime_data()
    db.add_registered_account({"email": "a@x.com", "session_token": "s1"})
    db.add_registered_account({"email": "b@x.com", "session_token": "s2"})
    db.add_registered_account({"email": "c@x.com", "session_token": "s3"})
    rows = db.iter_registered_accounts()
    ids = [r["id"] for r in rows[:2]]
    r = client.post("/api/inventory/accounts/delete", json={"ids": ids})
    assert r.status_code == 200
    assert r.json() == {"deleted": 2, "requested": 2}
    remaining = [r["email"] for r in db.iter_registered_accounts()]
    assert remaining == ["c@x.com"]


def test_check_requires_auth(client):
    r = client.post("/api/inventory/accounts/check", json={"ids": [1]})
    assert r.status_code == 401


def test_check_rejects_empty_ids(client):
    _login(client)
    r = client.post("/api/inventory/accounts/check", json={"ids": []})
    assert r.status_code == 400


def test_check_persists_results(client, monkeypatch):
    _login(client)
    db = get_db()
    db.clear_runtime_data()
    db.add_registered_account({"email": "valid@x.com", "session_token": "s1"})
    db.add_registered_account({"email": "invalid@x.com", "session_token": "s2"})
    db.add_registered_account({"email": "unknown@x.com", "session_token": "s3"})

    # mock the validator so tests don't hit chatgpt.com
    def fake(account, **kwargs):
        email = account.get("email", "")
        if email.startswith("valid"):
            return ("valid", "ok")
        if email.startswith("invalid"):
            return ("invalid", "http 403")
        return ("unknown", "timeout")
    monkeypatch.setattr("webui.backend.account_validator.validate_account", fake)

    ids = [r["id"] for r in db.iter_registered_accounts()]
    r = client.post("/api/inventory/accounts/check", json={"ids": ids})
    assert r.status_code == 200
    body = r.json()
    assert body["summary"] == {
        "total": 3,
        "valid": 1,
        "invalid": 1,
        "unknown": 1,
        "free": 0,
        "plus": 0,
        "team": 0,
        "pro": 0,
    }

    # results persisted
    by_email = {a["email"]: a for a in db.iter_registered_accounts()}
    assert by_email["valid@x.com"]["last_check_status"] == "valid"
    assert by_email["invalid@x.com"]["last_check_status"] == "invalid"
    assert by_email["unknown@x.com"]["last_check_status"] == "unknown"
    assert by_email["valid@x.com"]["last_check_at"] > 0


def test_check_persists_live_plan_type(client, monkeypatch):
    _login(client)
    db = get_db()
    db.clear_runtime_data()
    db.add_registered_account({
        "email": "live-plus@x.com",
        "session_token": "sess",
        "access_token": "header.payload.sig",
    })

    monkeypatch.setattr(
        "webui.backend.account_validator.validate_account",
        lambda account, **kwargs: ("unknown", "me: http 403"),
    )
    monkeypatch.setattr(
        "webui.backend.account_validator._probe_check_v4_plan",
        lambda access_token, timeout, proxy: ("valid", "plus", "check/v4 ok; plan=plus"),
    )

    account_id = db.iter_registered_accounts()[0]["id"]
    r = client.post("/api/inventory/accounts/check", json={"ids": [account_id]})
    assert r.status_code == 200
    body = r.json()
    assert body["summary"]["valid"] == 1
    assert body["summary"]["plus"] == 1

    row = db.get_registered_account(account_id)
    assert row["last_check_status"] == "valid"
    assert row["last_plan_type"] == "plus"
