from __future__ import annotations

from webui.backend.db import get_db


def _login(client):
    client.post("/api/setup", json={"username": "admin", "password": "hunter2hunter2"})
    client.post("/api/login", json={"username": "admin", "password": "hunter2hunter2"})


def test_mail_accounts_save_defaults_to_db(client):
    _login(client)

    r = client.post(
        "/api/mail/accounts/save",
        json={"accounts_text": "first@outlook.com----pw1\nsecond@gmail.com----pw2"},
    )

    assert r.status_code == 200
    body = r.json()
    assert body["path"] == "sqlite:mail_accounts"
    assert body["count"] == 2
    assert body["submitted_count"] == 2
    assert body["inserted_count"] == 2
    assert body["skipped_existing"] == 0
    assert body["total_count"] == 2
    rows = get_db().iter_mail_accounts()
    assert [row["email"] for row in rows] == ["first@outlook.com", "second@gmail.com"]
    assert rows[0]["mail_password"] == "pw1"


def test_mail_accounts_save_reports_existing_skips(client):
    _login(client)
    get_db().append_mail_accounts([
        {"email": "first@outlook.com", "mail_password": "old"},
    ])

    r = client.post(
        "/api/mail/accounts/save",
        json={"accounts_text": "first@outlook.com----new\nsecond@gmail.com----pw2"},
    )

    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 2
    assert body["submitted_count"] == 2
    assert body["inserted_count"] == 1
    assert body["skipped_existing"] == 1
    assert body["total_count"] == 2
    assert [a["email"] for a in body["accounts"]] == ["second@gmail.com"]
    rows = {row["email"]: row for row in get_db().iter_mail_accounts()}
    assert rows["first@outlook.com"]["mail_password"] == "old"


def test_mail_accounts_status_reads_db(client):
    _login(client)
    get_db().append_mail_accounts([
        {"email": "first@outlook.com", "mail_password": "pw1", "provider": "outlook"},
    ])

    r = client.get("/api/mail/accounts/status")

    assert r.status_code == 200
    body = r.json()
    assert body["path"] == "sqlite:mail_accounts"
    assert body["count"] == 1
    assert body["accounts"][0]["email"] == "first@outlook.com"


def test_mail_accounts_list_uses_db_pool(client, monkeypatch):
    _login(client)
    get_db().append_mail_accounts([
        {"email": "first@outlook.com", "mail_password": "pw1", "provider": "outlook"},
    ])

    class FakeProvider:
        def __init__(self, account):
            self.account = account

        def list_messages(self, limit=10):
            return [{"uid": "1", "subject": "OpenAI code 123456"}]

    import webui.backend.routes.mail_accounts as route_mod

    monkeypatch.setattr(route_mod, "ImapOtpProvider", FakeProvider)
    r = client.post("/api/mail/accounts/list", json={"limit": 5})

    assert r.status_code == 200
    body = r.json()
    assert body["email"] == "first@outlook.com"
    assert body["count"] == 1


def test_mail_accounts_list_prefers_graph_for_outlook_token(client, monkeypatch):
    _login(client)
    get_db().append_mail_accounts([
        {
            "email": "first@outlook.com",
            "mail_password": "pw1",
            "provider": "outlook",
            "account_id": "client-id",
            "refresh_token": "refresh-token",
        },
    ])
    calls = []

    class FakeGraphProvider:
        def __init__(self, account):
            calls.append(("graph_init", account.email))

        def list_messages(self, limit=10):
            calls.append(("graph_list", limit))
            return [{"uid": "g1", "subject": "OpenAI code 123456"}]

    class FakeImapProvider:
        def __init__(self, account):
            raise AssertionError("IMAP should not be used when Graph succeeds")

    import webui.backend.routes.mail_accounts as route_mod

    monkeypatch.setattr(route_mod, "GraphOtpProvider", FakeGraphProvider)
    monkeypatch.setattr(route_mod, "ImapOtpProvider", FakeImapProvider)

    r = client.post("/api/mail/accounts/list", json={"limit": 5})

    assert r.status_code == 200
    body = r.json()
    assert body["email"] == "first@outlook.com"
    assert body["protocol"] == "graph"
    assert body["messages"] == [{"uid": "g1", "subject": "OpenAI code 123456"}]
    assert calls == [("graph_init", "first@outlook.com"), ("graph_list", 5)]


def test_mail_accounts_list_falls_back_to_imap_when_graph_fails(client, monkeypatch):
    _login(client)
    get_db().append_mail_accounts([
        {
            "email": "first@outlook.com",
            "mail_password": "pw1",
            "provider": "outlook",
            "account_id": "client-id",
            "refresh_token": "refresh-token",
        },
    ])
    calls = []

    class FakeGraphProvider:
        def __init__(self, account):
            calls.append(("graph_init", account.email))

        def list_messages(self, limit=10):
            calls.append(("graph_list", limit))
            raise RuntimeError("Graph 403 Mail.Read missing")

    class FakeImapProvider:
        def __init__(self, account):
            calls.append(("imap_init", account.email))

        def list_messages(self, limit=10):
            calls.append(("imap_list", limit))
            return [{"uid": "i1", "subject": "OpenAI code 654321"}]

    import webui.backend.routes.mail_accounts as route_mod

    monkeypatch.setattr(route_mod, "GraphOtpProvider", FakeGraphProvider)
    monkeypatch.setattr(route_mod, "ImapOtpProvider", FakeImapProvider)

    r = client.post("/api/mail/accounts/list", json={"limit": 7})

    assert r.status_code == 200
    body = r.json()
    assert body["protocol"] == "imap"
    assert body["messages"] == [{"uid": "i1", "subject": "OpenAI code 654321"}]
    assert calls == [
        ("graph_init", "first@outlook.com"),
        ("graph_list", 7),
        ("imap_init", "first@outlook.com"),
        ("imap_list", 7),
    ]
