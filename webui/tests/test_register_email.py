from __future__ import annotations

import json
import sys
from pathlib import Path

import pipeline
from webui.backend.db import get_db


ROOT = Path(__file__).resolve().parents[2]
CTF_REG_DIR = ROOT / "CTF-reg"
if str(CTF_REG_DIR) not in sys.path:
    sys.path.insert(0, str(CTF_REG_DIR))

from mail_provider import MailProvider  # noqa: E402


def test_imap_list_reserves_specified_email_instead_of_first_unused(tmp_path, monkeypatch):
    monkeypatch.setenv("WEBUI_DATA_DIR", str(tmp_path))
    db = get_db()
    db.clear_runtime_data()
    db.append_mail_accounts([
        {
            "email": "first@example.test",
            "mail_password": "first-pw",
            "provider": "custom",
            "status": "unused",
        },
        {
            "email": "Target@outlook.com",
            "mail_password": "target-pw",
            "provider": "outlook",
            "status": "unused",
        },
    ])

    mail = MailProvider("", mode="imap_list")

    reserved_email = mail.reserve_email("target@outlook.com")
    mailbox_email = mail.create_mailbox()

    assert reserved_email == "target@outlook.com"
    assert mailbox_email == "target@outlook.com"
    assert db.find_mail_account("first@example.test")["status"] == "unused"
    assert db.find_mail_account("target@outlook.com")["status"] == "reserved"


def test_register_passes_register_email_to_child_process(tmp_path, monkeypatch):
    monkeypatch.setenv("WEBUI_DATA_DIR", str(tmp_path))
    config_path = tmp_path / "reg.json"
    config_path.write_text(json.dumps({"mail": {"mode": "imap_list"}}), encoding="utf-8")
    captured = {}

    class FakeProc:
        returncode = 0

        def __init__(self):
            self.stdout = iter([
                'LOCALAUTH_RESULT_JSON={"email":"target@outlook.com","session_token":"sess"}\n'
            ])

        def wait(self):
            return 0

        def kill(self):
            raise AssertionError("timeout path should not be used")

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return FakeProc()

    monkeypatch.setattr(pipeline.subprocess, "Popen", fake_popen)

    result = pipeline.register(
        str(config_path),
        register_method="protocol",
        register_email="Target@outlook.com",
        mail_fetch_protocol="imap",
    )

    assert result["email"] == "target@outlook.com"
    assert captured["cmd"][0] == sys.executable
    assert captured["cmd"][-1] == "Target@outlook.com"
    assert "target_email = sys.argv[3]" in captured["cmd"][2]
    assert captured["kwargs"]["env"]["MAIL_FETCH_PROTOCOL"] == "imap"
