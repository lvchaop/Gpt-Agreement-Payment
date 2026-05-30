import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _load_module(name: str, rel_path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_paypal_hero_sms_requires_activation_id(tmp_path, monkeypatch):
    card = _load_module("ctf_pay_card_hero_requires_activation_test", "CTF-pay/card.py")
    monkeypatch.setattr(card, "_log", lambda *_args, **_kwargs: None)
    phones = tmp_path / "phones.jsonl"
    phones.write_text('{"phone":"+817012345678","country":"JP"}\n', encoding="utf-8")

    cfg = {
        "sms_provider": "hero_sms",
        "sms_api_enabled": True,
        "phones_file": str(phones),
        "phone_country": "JP",
        "hero_sms": {"api_key": "hero-key"},
    }

    try:
        card._paypal_resolve_new_user_phone(cfg, {})
    except RuntimeError as e:
        assert "activation_id" in str(e)
        assert "getStatusV2" in str(e)
    else:
        raise AssertionError("expected Hero SMS without activation_id to fail clearly")


def test_paypal_hero_sms_can_use_activation_id_for_status_url(tmp_path, monkeypatch):
    card = _load_module("ctf_pay_card_hero_activation_test", "CTF-pay/card.py")
    monkeypatch.setattr(card, "_log", lambda *_args, **_kwargs: None)
    phones = tmp_path / "phones.jsonl"
    phones.write_text(
        '{"phone":"+817012345678","country":"JP","activation_id":"hero-123"}\n',
        encoding="utf-8",
    )

    cfg = {
        "sms_provider": "hero_sms",
        "sms_api_enabled": True,
        "phones_file": str(phones),
        "phone_country": "JP",
        "hero_sms": {
            "base_url": "https://hero-sms.com/stubs/handler_api.php",
            "api_key": "hero-key",
        },
    }

    phone = card._paypal_resolve_new_user_phone(cfg, {})
    url = card._paypal_sms_api_url(cfg, phone["phone"])

    assert phone["phone"] == "+817012345678"
    assert "action=getStatusV2" in url
    assert "api_key=hero-key" in url
    assert "id=hero-123" in url


def test_paypal_hero_sms_builds_set_status_after_otp_url(tmp_path, monkeypatch):
    card = _load_module("ctf_pay_card_hero_set_status_test", "CTF-pay/card.py")
    monkeypatch.setattr(card, "_log", lambda *_args, **_kwargs: None)
    phones = tmp_path / "phones.jsonl"
    phones.write_text(
        '{"phone":"+817012345678","country":"JP","activation_id":"hero-123"}\n',
        encoding="utf-8",
    )

    cfg = {
        "sms_provider": "hero_sms",
        "sms_api_enabled": True,
        "phones_file": str(phones),
        "phone_country": "JP",
        "hero_sms": {
            "base_url": "https://hero-sms.com/stubs/handler_api.php",
            "api_key": "hero-key",
        },
    }

    card._paypal_resolve_new_user_phone(cfg, {})
    url = card._hero_sms_set_status_after_otp_url(cfg)

    assert "action=setStatus" in url
    assert "api_key=hero-key" in url
    assert "id=hero-123" in url
    assert "status=3" in url


def test_paypal_hero_sms_template_uses_activation_id(tmp_path, monkeypatch):
    card = _load_module("ctf_pay_card_hero_template_test", "CTF-pay/card.py")
    monkeypatch.setattr(card, "_log", lambda *_args, **_kwargs: None)
    phones = tmp_path / "phones.jsonl"
    phones.write_text(
        '{"phone":"+817012345678","country":"JP","activation_id":"hero-123"}\n',
        encoding="utf-8",
    )

    cfg = {
        "sms_provider": "hero_sms",
        "sms_api_enabled": True,
        "phones_file": str(phones),
        "phone_country": "JP",
        "sms_api_url_template": "https://nexsms.example/should-not-be-used?phone={phone}",
        "hero_sms": {
            "api_key": "hero-key",
            "sms_api_url_template": "https://hero.example/sms?key={api_key_raw}&id={activation_id}",
        },
    }

    phone = card._paypal_resolve_new_user_phone(cfg, {})
    url = card._paypal_sms_api_url(cfg, phone["phone"])

    assert phone["phone"] == "+817012345678"
    assert url == "https://hero.example/sms?key=hero-key&id=hero-123"


def test_paypal_delayed_phone_lease_is_not_acquired_until_node_form_fill(tmp_path, monkeypatch):
    card = _load_module("ctf_pay_card_delayed_phone_lease_test", "CTF-pay/card.py")
    monkeypatch.setattr(card, "_log", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        card,
        "_paypal_resolve_new_user_address",
        lambda *_args, **_kwargs: {
            "country": "US",
            "line1": "1 Example St",
            "city": "New York",
            "state": "NY",
            "postal_code": "10001",
            "first_name": "Ann",
            "last_name": "Lee",
            "full_name": "Ann Lee",
        },
    )
    phones = tmp_path / "phones.jsonl"
    phones.write_text(
        '{"phone":"2015550101","country":"US"}\n'
        '{"phone":"2015550102","country":"US"}\n',
        encoding="utf-8",
    )
    lease_dir = tmp_path / "leases"
    available = lease_dir / "available"
    leased = lease_dir / "leased"
    available.mkdir(parents=True)
    leased.mkdir()
    (available / "0").write_text("", encoding="utf-8")
    (available / "1").write_text("", encoding="utf-8")

    cfg = {
        "flow": "new_user",
        "phones_file": str(phones),
        "phone_country": "US",
        "_batch_phone_lease_dir": str(lease_dir),
        "_defer_phone_lease_to_node_rpa": True,
    }

    phone, _signup_card, _address = card._paypal_signup_payloads(
        cfg,
        {},
        {"number": "4111111111111111", "expiry": "12/30", "cvc": "123"},
    )

    assert phone == ""
    assert "phone_index" not in cfg
    assert (available / "0").exists()
    assert not list(leased.iterdir())


def test_paypal_sms_extracts_hero_status_json():
    signup = _load_module("paypal_plus_signup_hero_extract_test", "CTF-reg/paypal_plus/signup.py")

    raw = '{"sms":{"code":"654321","text":"PayPal code 654321"},"verificationType":"sms"}'

    assert signup._extract_sms_code_from_text(raw) == "654321"


def test_paypal_phone_otp_lock_serializes_same_phone(tmp_path, monkeypatch):
    signup = _load_module("paypal_plus_signup_phone_lock_test", "CTF-reg/paypal_plus/signup.py")
    monkeypatch.setenv("PPS_PAYPAL_PHONE_LOCK_DIR", str(tmp_path / "locks"))

    first = signup._PhoneOtpLock("+81 70-1234-5678", timeout=1, stale_after=60)
    second = signup._PhoneOtpLock("+817012345678", timeout=1, stale_after=60)
    first.acquire()
    try:
        try:
            second.acquire()
        except TimeoutError:
            pass
        else:
            raise AssertionError("same phone should be locked until the first holder releases")
    finally:
        first.release()

    second.acquire()
    second.release()
