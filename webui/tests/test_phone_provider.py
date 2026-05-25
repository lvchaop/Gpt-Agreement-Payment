import importlib.util
import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("phone_provider_mod", ROOT / "CTF-reg" / "phone_provider.py")
assert SPEC and SPEC.loader
phone_provider = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = phone_provider
SPEC.loader.exec_module(phone_provider)


class _Resp:
    def __init__(self, text: str):
        self.text = text

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.text.encode("utf-8")


class _HeroOpener:
    def __init__(self):
        self.urls = []

    def open(self, req, timeout=0):
        self.urls.append(req.full_url)
        if "action=getNumberV2" in req.full_url:
            return _Resp(json.dumps({
                "activationId": "635468024",
                "phoneNumber": "81234567890",
                "countryPhoneCode": 62,
                "activationEndTime": "2026-02-18T18:11:23+00:00",
            }))
        if "action=getStatusV2" in req.full_url:
            return _Resp(json.dumps({
                "verificationType": 2,
                "sms": {
                    "dateTime": "2026-02-18 16:12:33",
                    "code": "654321",
                    "text": "Your code is 654321",
                },
                "call": {
                    "from": "",
                    "text": "",
                    "code": "",
                    "dateTime": "0000-00-00 00:00:00",
                    "url": "",
                    "parsingCount": 0,
                },
            }))
        if "action=setStatus" in req.full_url:
            return _Resp("ACCESS_ACTIVATION")
        return _Resp("BAD_ACTION")


def _cfg(**overrides):
    data = {
        "enabled": True,
        "provider": "hero_sms",
        "base_url": "https://hero-sms.com/stubs/handler_api.php",
        "api_key": "secret-token",
        "api_key_env": "",
        "country": "2",
        "service": "tg",
        "request_timeout_s": 1,
        "otp_timeout_s": 3,
        "otp_poll_interval_s": 0.01,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def test_hero_sms_v2_allocate_poll_and_status():
    provider = phone_provider.PhoneProvider.from_config(_cfg(maxPrice="12.5"))
    opener = _HeroOpener()
    provider.opener = opener

    lease = provider.allocate()
    code = provider.poll_otp(lease.lease_id)
    provider.mark_verified(lease.lease_id)

    assert lease.lease_id == "635468024"
    assert lease.phone_e164 == "+6281234567890"
    assert lease.phone_national == "81234567890"
    assert lease.country_phone_code == "62"
    assert lease.masked_phone.startswith("+6")
    assert lease.expires_at == "2026-02-18T18:11:23+00:00"
    assert code == "654321"
    assert any("action=getNumberV2" in u and "service=tg" in u and "country=2" in u and "maxPrice=12.5" in u for u in opener.urls)
    assert any("action=getStatusV2" in u and "id=635468024" in u for u in opener.urls)
    assert any("action=setStatus" in u and "status=6" in u for u in opener.urls)


def test_hero_sms_country_pool_uses_country_specific_max_price():
    provider = phone_provider.PhoneProvider.from_config(_cfg(
        country="2",
        countries=["151"],
        maxPrice="12.5",
        country_max_prices={"151": "0.1"},
    ))
    opener = _HeroOpener()
    provider.opener = opener

    provider.allocate()

    assert any(
        "action=getNumberV2" in u and "country=151" in u and "maxPrice=0.1" in u
        for u in opener.urls
    )


def test_hero_sms_allocate_retries_http_409():
    class ConflictThenOkOpener(_HeroOpener):
        def __init__(self):
            super().__init__()
            self.get_number_calls = 0

        def open(self, req, timeout=0):
            self.urls.append(req.full_url)
            if "action=getNumberV2" in req.full_url:
                self.get_number_calls += 1
                if self.get_number_calls == 1:
                    raise HTTPError(req.full_url, 409, "Conflict", {}, io.BytesIO(b'{"message":"conflict"}'))
            return super().open(req, timeout=timeout)

    provider = phone_provider.PhoneProvider.from_config(_cfg(max_number_attempts=2))
    opener = ConflictThenOkOpener()
    provider.opener = opener

    lease = provider.allocate()

    assert lease.lease_id == "635468024"
    assert opener.get_number_calls == 2


def test_hero_sms_poll_retries_http_409():
    class StatusConflictThenOkOpener(_HeroOpener):
        def __init__(self):
            super().__init__()
            self.status_calls = 0

        def open(self, req, timeout=0):
            self.urls.append(req.full_url)
            if "action=getStatusV2" in req.full_url:
                self.status_calls += 1
                if self.status_calls == 1:
                    raise HTTPError(req.full_url, 409, "Conflict", {}, io.BytesIO(b'{"message":"conflict"}'))
            return super().open(req, timeout=timeout)

    provider = phone_provider.PhoneProvider.from_config(_cfg())
    opener = StatusConflictThenOkOpener()
    provider.opener = opener

    lease = provider.allocate()
    code = provider.poll_otp(lease.lease_id)

    assert code == "654321"
    assert opener.status_calls == 2


def test_hero_sms_status_v2_can_read_call_code():
    class CallOpener(_HeroOpener):
        def open(self, req, timeout=0):
            self.urls.append(req.full_url)
            if "action=getNumberV2" in req.full_url:
                return _Resp(json.dumps({
                    "activationId": "635468024",
                    "phoneNumber": "81234567890",
                    "countryPhoneCode": 62,
                }))
            if "action=getStatusV2" in req.full_url:
                return _Resp(json.dumps({
                    "verificationType": 1,
                    "sms": {
                        "dateTime": "0000-00-00 00:00:00",
                        "code": "",
                        "text": "",
                    },
                    "call": {
                        "from": "phone",
                        "text": "voice text",
                        "code": "12345",
                        "dateTime": "2026-02-18 16:12:33",
                        "url": "voice file url",
                        "parsingCount": 1,
                    },
                }))
            return _Resp("ACCESS_ACTIVATION")

    provider = phone_provider.PhoneProvider.from_config(_cfg())
    provider.opener = CallOpener()

    lease = provider.allocate()
    assert provider.poll_otp(lease.lease_id) == "12345"


def test_hero_sms_rejects_masked_number():
    class MaskedOpener(_HeroOpener):
        def open(self, req, timeout=0):
            return _Resp(json.dumps({
                "activationId": "635468024",
                "phoneNumber": "79584******",
                "countryPhoneCode": 62,
            }))

    provider = phone_provider.PhoneProvider.from_config(_cfg())
    provider.opener = MaskedOpener()

    try:
        provider.allocate()
    except RuntimeError as e:
        assert "脱敏手机号" in str(e)
    else:
        raise AssertionError("masked number should fail")
