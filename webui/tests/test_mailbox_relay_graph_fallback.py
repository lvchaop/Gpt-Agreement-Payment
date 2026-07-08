from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CTF_REG_DIR = ROOT / "CTF-reg"
if str(CTF_REG_DIR) not in sys.path:
    sys.path.insert(0, str(CTF_REG_DIR))

from email_account_pool import EmailAccount  # noqa: E402
from graph_otp_provider import GraphOtpProvider  # noqa: E402
from imap_otp_provider import OtpMatch  # noqa: E402
import mailbox_relay  # noqa: E402


class FakeKV:
    def __init__(self):
        self.writes = []

    def put_otp(self, email_addr, otp, *, metadata=None, ttl=600):
        self.writes.append({
            "email_addr": email_addr,
            "otp": otp,
            "metadata": metadata,
            "ttl": ttl,
        })
        return {"success": True}


class FakeHTTPResponse:
    def __init__(self, body: bytes):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self.body


def _outlook_account(**kwargs):
    data = {
        "email": "first@outlook.com",
        "mail_password": "imap-pw",
        "provider": "outlook",
        "account_id": "client-id",
        "refresh_token": "refresh-token",
    }
    data.update(kwargs)
    return EmailAccount(**data)


def test_mailbox_relay_prefers_graph_for_outlook_token(monkeypatch):
    calls = []

    class FakeGraphProvider:
        def __init__(self, account, mark_seen=False):
            calls.append(("graph_init", account.email, mark_seen))

        def wait_for_otp_match(self, email_addr, *, timeout=180, issued_after=None):
            calls.append(("graph_wait", email_addr, timeout, issued_after))
            return OtpMatch(
                otp="111111",
                uid="graph-1",
                subject="OpenAI code",
                source="graph",
            )

    class FakeImapProvider:
        def __init__(self, account, mark_seen=False):
            raise AssertionError("IMAP should not be used when Graph succeeds")

    monkeypatch.setattr(mailbox_relay, "GraphOtpProvider", FakeGraphProvider)
    monkeypatch.setattr(mailbox_relay, "ImapOtpProvider", FakeImapProvider)

    kv = FakeKV()
    relay = mailbox_relay.MailboxRelay(kv, mark_seen=True)
    payload = relay.relay_until_otp(
        _outlook_account(),
        "first@outlook.com",
        timeout=9,
        issued_after=123.0,
    )

    assert payload["otp"] == "111111"
    assert payload["source"] == "graph"
    assert kv.writes[0]["metadata"]["uid"] == "graph-1"
    assert calls == [
        ("graph_init", "first@outlook.com", True),
        ("graph_wait", "first@outlook.com", 9, 123.0),
    ]


def test_mailbox_relay_falls_back_to_imap_when_graph_fails(monkeypatch):
    calls = []

    class FakeGraphProvider:
        def __init__(self, account, mark_seen=False):
            calls.append(("graph_init", account.email, mark_seen))

        def wait_for_otp_match(self, email_addr, *, timeout=180, issued_after=None):
            calls.append(("graph_wait", email_addr, timeout, issued_after))
            raise RuntimeError("Graph 403 Mail.Read missing")

    class FakeImapProvider:
        def __init__(self, account, mark_seen=False):
            calls.append(("imap_init", account.email, mark_seen))

        def wait_for_otp_match(self, email_addr, *, timeout=180, issued_after=None):
            calls.append(("imap_wait", email_addr, timeout, issued_after))
            return OtpMatch(
                otp="222222",
                uid="imap-1",
                subject="OpenAI code",
                source="imap_list",
            )

    monkeypatch.setattr(mailbox_relay, "GraphOtpProvider", FakeGraphProvider)
    monkeypatch.setattr(mailbox_relay, "ImapOtpProvider", FakeImapProvider)

    kv = FakeKV()
    relay = mailbox_relay.MailboxRelay(kv, mark_seen=False)
    payload = relay.relay_until_otp(
        _outlook_account(),
        "first@outlook.com",
        timeout=7,
        issued_after=456.0,
    )

    assert payload["otp"] == "222222"
    assert payload["source"] == "imap_list"
    assert kv.writes[0]["metadata"]["uid"] == "imap-1"
    assert calls == [
        ("graph_init", "first@outlook.com", False),
        ("graph_wait", "first@outlook.com", 7, 456.0),
        ("imap_init", "first@outlook.com", False),
        ("imap_wait", "first@outlook.com", 7, 456.0),
    ]


def test_mailbox_relay_uses_imap_for_outlook_without_token(monkeypatch):
    calls = []

    class FakeGraphProvider:
        def __init__(self, account, mark_seen=False):
            raise AssertionError("Graph should not be used without OAuth token")

    class FakeImapProvider:
        def __init__(self, account, mark_seen=False):
            calls.append(("imap_init", account.email, mark_seen))

        def wait_for_otp_match(self, email_addr, *, timeout=180, issued_after=None):
            calls.append(("imap_wait", email_addr, timeout, issued_after))
            return OtpMatch(otp="333333", uid="imap-2", source="imap_list")

    monkeypatch.setattr(mailbox_relay, "GraphOtpProvider", FakeGraphProvider)
    monkeypatch.setattr(mailbox_relay, "ImapOtpProvider", FakeImapProvider)

    kv = FakeKV()
    relay = mailbox_relay.MailboxRelay(kv)
    payload = relay.relay_until_otp(
        _outlook_account(account_id="", refresh_token="", access_token=""),
        "first@outlook.com",
        timeout=5,
        issued_after=789.0,
    )

    assert payload["otp"] == "333333"
    assert calls == [
        ("imap_init", "first@outlook.com", False),
        ("imap_wait", "first@outlook.com", 5, 789.0),
    ]


def test_mailbox_relay_force_imap_skips_graph_for_outlook_token(monkeypatch):
    calls = []

    class FakeGraphProvider:
        def __init__(self, account, mark_seen=False):
            raise AssertionError("Graph should not be used when MAIL_FETCH_PROTOCOL=imap")

    class FakeImapProvider:
        def __init__(self, account, mark_seen=False):
            calls.append(("imap_init", account.email, mark_seen))

        def wait_for_otp_match(self, email_addr, *, timeout=180, issued_after=None):
            calls.append(("imap_wait", email_addr, timeout, issued_after))
            return OtpMatch(otp="555555", uid="imap-forced", source="imap_list")

    monkeypatch.setenv("MAIL_FETCH_PROTOCOL", "imap")
    monkeypatch.setattr(mailbox_relay, "GraphOtpProvider", FakeGraphProvider)
    monkeypatch.setattr(mailbox_relay, "ImapOtpProvider", FakeImapProvider)

    kv = FakeKV()
    relay = mailbox_relay.MailboxRelay(kv)
    payload = relay.relay_until_otp(
        _outlook_account(),
        "first@outlook.com",
        timeout=6,
        issued_after=111.0,
    )

    assert payload["otp"] == "555555"
    assert calls == [
        ("imap_init", "first@outlook.com", False),
        ("imap_wait", "first@outlook.com", 6, 111.0),
    ]


def test_graph_provider_extracts_openai_otp_from_graph_message(monkeypatch):
    account = _outlook_account(access_token="access-token")
    provider = GraphOtpProvider(account)

    def fake_graph_get(path, params):
        assert path == "/me/mailFolders/inbox/messages"
        assert params["$select"] == "id,receivedDateTime,from,sender,subject,bodyPreview,body"
        return {
            "value": [
                {
                    "id": "msg-1",
                    "receivedDateTime": "2026-07-08T10:00:00Z",
                    "from": {
                        "emailAddress": {
                            "name": "OpenAI",
                            "address": "noreply@tm.openai.com",
                        },
                    },
                    "subject": "Your ChatGPT code",
                    "bodyPreview": "Your verification code is 444444.",
                    "body": {
                        "contentType": "text",
                        "content": "Your verification code is 444444.",
                    },
                }
            ]
        }

    monkeypatch.setattr(provider, "_graph_get", fake_graph_get)

    messages = provider.list_messages(limit=5)
    match = provider.wait_for_otp_match("first@outlook.com", timeout=1, issued_after=0)

    assert messages == [
        {
            "uid": "msg-1",
            "date": "2026-07-08T10:00:00Z",
            "from": "OpenAI <noreply@tm.openai.com>",
            "subject": "Your ChatGPT code",
            "snippet": "Your verification code is 444444.",
        }
    ]
    assert match.otp == "444444"
    assert match.source == "graph"


def test_graph_provider_token_exchange_uses_default_scope(monkeypatch):
    account = _outlook_account(access_token="")
    provider = GraphOtpProvider(account)
    captured = []

    class FakeOpener:
        def open(self, req, timeout=0):
            captured.append(req)
            return FakeHTTPResponse(
                b'{"access_token":"graph-access","scope":"User.Read Mail.Read profile","refresh_token":"rt-new"}'
            )

    provider._opener = FakeOpener()

    provider._ensure_access_token()

    body = captured[0].data.decode()
    assert "scope=https%3A%2F%2Fgraph.microsoft.com%2F.default" in body
    assert account.access_token == "graph-access"
    assert account.refresh_token == "rt-new"


def test_graph_provider_rejects_token_without_mail_read_scope(monkeypatch):
    account = _outlook_account(access_token="")
    provider = GraphOtpProvider(account)

    class FakeOpener:
        def open(self, req, timeout=0):
            return FakeHTTPResponse(
                b'{"access_token":"graph-access","scope":"User.Read profile"}'
            )

    provider._opener = FakeOpener()

    try:
        provider._ensure_access_token()
    except RuntimeError as exc:
        assert "scope missing Mail.Read/Mail.ReadWrite" in str(exc)
    else:
        raise AssertionError("expected Graph token without Mail.Read to be rejected")
