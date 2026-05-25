import pytest
from webui.backend.db import Database


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "test.db")


def test_create_and_verify_user(db):
    db.create_user("admin", "secret")
    assert db.verify_user("admin", "secret") is True
    assert db.verify_user("admin", "wrong") is False
    assert db.verify_user("nobody", "secret") is False


def test_user_count_distinguishes_uninitialized(db):
    assert db.user_count() == 0
    db.create_user("admin", "secret")
    assert db.user_count() == 1


def test_session_create_lookup_delete(db):
    db.create_user("admin", "secret")
    sid = db.create_session("admin")
    assert db.lookup_session(sid) == "admin"
    db.delete_session(sid)
    assert db.lookup_session(sid) is None


def test_session_expires(db, monkeypatch):
    import webui.backend.db as db_mod
    db.create_user("admin", "secret")
    times = [1000.0]
    monkeypatch.setattr(db_mod.time, "time", lambda: times[0])
    sid = db.create_session("admin", ttl_s=60)
    times[0] = 1061.0  # past TTL
    assert db.lookup_session(sid) is None


def test_clear_runtime_data_preserves_durable_runtime_config(db):
    db.set_runtime_json("secrets", {"cloudflare": {"api_token": "tok"}})
    db.set_runtime_json("wizard_state", {"current_step": 4, "answers": {}})
    db.set_runtime_json("wa_settings", {"engine": "baileys"})
    db.set_runtime_json("wa_session_snapshot", {"data": "snapshot"})
    db.set_runtime_json("daemon_state", {"old": True})
    db.set_runtime_json("wa_state", {"latest": {"otp": "123456"}})
    db.add_registered_account({"email": "a@example.com", "session_token": "sess"})
    db.add_card_result({"chatgpt_email": "a@example.com", "status": "succeeded"})
    db.append_mail_accounts([{"email": "mail@example.com", "mail_password": "pw"}])

    db.clear_runtime_data()

    assert db.iter_registered_accounts() == []
    assert db.iter_card_results() == []
    assert db.iter_mail_accounts()[0]["email"] == "mail@example.com"
    assert db.get_runtime_json("secrets", {})["cloudflare"]["api_token"] == "tok"
    assert db.get_runtime_json("wizard_state", {})["current_step"] == 4
    assert db.get_runtime_json("wa_settings", {})["engine"] == "baileys"
    assert db.get_runtime_json("wa_session_snapshot", {})["data"] == "snapshot"
    assert db.get_runtime_json("daemon_state", {}) == {}
    assert db.get_runtime_json("wa_state", {}) == {}


def test_registered_account_stores_phone_registration_fields(db):
    db.add_registered_account({
        "email": "phone@example.com",
        "register_method": "phone_browser",
        "phone_number": "81234567890",
        "phone_dial_code": "62",
        "phone_country": "2",
    })

    row = db.iter_registered_accounts()[0]
    assert row["register_method"] == "phone_browser"
    assert row["phone_number"] == "81234567890"
    assert row["phone_dial_code"] == "62"
    assert row["phone_country"] == "2"


def test_registered_account_has_sale_state_fields(db):
    db.add_registered_account({"email": "sale@example.com", "session_token": "sess"})

    row = db.iter_registered_accounts()[0]
    assert row["sale_status"] == "available"
    assert row["sold_at"] == 0
    assert row["sale_note"] == ""


def test_claim_account_for_sale_marks_one_available_plus_account(db):
    db.add_registered_account({"email": "nopass-plus@example.com", "password": ""})
    db.add_card_result({"chatgpt_email": "nopass-plus@example.com", "status": "succeeded"})
    db.add_registered_account({"email": "free@example.com", "password": "pfree"})
    db.add_registered_account({"email": "team@example.com", "password": "pteam"})
    db.add_card_result({"chatgpt_email": "team@example.com", "status": "succeeded", "team_account_id": "team-1"})
    db.add_registered_account({"email": "first@example.com", "password": "p1"})
    db.upsert_mail_accounts([{"email": "first@example.com", "mail_password": "mail-p1"}])
    db.add_card_result({"chatgpt_email": "first@example.com", "status": "succeeded"})
    db.add_registered_account({"email": "second@example.com", "password": "p2"})
    db.upsert_mail_accounts([{"email": "second@example.com", "mail_password": "mail-p2"}])
    db.add_pipeline_result({
        "registration": {"status": "ok", "email": "second@example.com"},
        "payment": {"status": "succeeded", "email": "second@example.com"},
    })

    claimed = db.claim_account_for_sale("order-1")

    assert claimed["email"] == "first@example.com"
    assert claimed["password"] == "p1"
    assert claimed["gpt_password"] == "p1"
    assert claimed["mail_password"] == "mail-p1"
    assert claimed["sale_status"] == "sold"
    assert claimed["sold_at"] > 0
    assert claimed["sale_note"] == "order-1"

    by_email = {row["email"]: row for row in db.iter_registered_accounts()}
    assert by_email["nopass-plus@example.com"]["sale_status"] == "available"
    assert by_email["free@example.com"]["sale_status"] == "available"
    assert by_email["team@example.com"]["sale_status"] == "available"
    assert by_email["first@example.com"]["sale_status"] == "sold"
    assert by_email["first@example.com"]["sale_note"] == "order-1"
    assert by_email["second@example.com"]["sale_status"] == "available"

    claimed2 = db.claim_account_for_sale("order-2")
    assert claimed2["email"] == "second@example.com"
    assert claimed2["mail_password"] == "mail-p2"
    assert db.claim_account_for_sale("order-3") == {}


def test_toggle_account_sale_status(db):
    db.add_registered_account({"email": "toggle@example.com", "password": "pw"})
    account_id = db.iter_registered_accounts()[0]["id"]

    sold = db.toggle_account_sale_status(account_id, "manual sold")
    assert sold["email"] == "toggle@example.com"
    assert sold["sale_status"] == "sold"
    assert sold["sold_at"] > 0
    assert sold["sale_note"] == "manual sold"

    available = db.toggle_account_sale_status(account_id)
    assert available["sale_status"] == "available"
    assert available["sold_at"] == 0
    assert available["sale_note"] == ""

    assert db.toggle_account_sale_status(999999) == {}


def test_mail_accounts_append_reserve_mark_and_find(db):
    count = db.append_mail_accounts([
        {"email": "first@outlook.com", "mail_password": "pw1", "provider": "outlook"},
        {"email": "second@gmail.com", "mail_password": "pw2", "provider": "gmail", "status": "used"},
    ])

    assert count == 2
    rows = db.iter_mail_accounts()
    assert [row["email"] for row in rows] == ["first@outlook.com", "second@gmail.com"]
    assert rows[0]["status"] == "unused"
    assert rows[0]["imap_port"] == "993"

    reserved = db.reserve_mail_account()
    assert reserved["email"] == "first@outlook.com"
    assert reserved["status"] == "reserved"
    assert db.reserve_mail_account() == {}

    assert db.find_mail_account("FIRST@OUTLOOK.COM")["status"] == "reserved"
    assert db.mark_mail_account("first@outlook.com", "failed", "login failed") is True
    assert db.find_mail_account("first@outlook.com")["status"] == "failed"
    assert db.find_mail_account("first@outlook.com")["fail_reason"] == "login failed"


def test_mail_accounts_append_skips_existing_email(db):
    db.append_mail_accounts([{"email": "same@example.com", "mail_password": "old", "status": "used"}])

    count = db.append_mail_accounts([
        {"email": "same@example.com", "mail_password": "new", "status": "unused"},
        {"email": "new@example.com", "mail_password": "pw"},
    ])

    assert count == 1
    by_email = {row["email"]: row for row in db.iter_mail_accounts()}
    assert by_email["same@example.com"]["mail_password"] == "old"
    assert by_email["same@example.com"]["status"] == "used"
    assert by_email["new@example.com"]["status"] == "unused"
