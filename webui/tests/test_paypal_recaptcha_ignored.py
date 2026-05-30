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


def test_paypal_authchallenge_recaptcha_is_ignored(monkeypatch):
    signup = _load_module("paypal_plus_signup_recaptcha_ignore_test", "CTF-reg/paypal_plus/signup.py")

    monkeypatch.setattr(
        signup,
        "_validate_paypal_recaptcha",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("recaptcha solver should not run")),
    )

    html = """
    <html data-captcha-type="recaptcha">
      <iframe src="https://www.paypal.com/recaptcha/recaptcha_v3.html?sitekey=site-key&action=default"></iframe>
    </html>
    """

    assert signup._validate_paypal_authchallenge(
        object(),
        challenge_html=html,
        signup_url="https://www.paypal.com/checkoutweb/signup?token=EC-TEST",
        proxy=None,
        timeout=1,
    ) is True


def test_paypal_recaptcha_validator_is_noop(monkeypatch):
    signup = _load_module("paypal_plus_signup_recaptcha_noop_test", "CTF-reg/paypal_plus/signup.py")

    monkeypatch.setattr(
        signup,
        "_solve_recaptcha_v3_token_protocol",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("recaptcha token solver should not run")),
    )

    assert signup._validate_paypal_recaptcha(
        object(),
        challenge_html='<iframe src="https://www.paypal.com/recaptcha/recaptcha_v3.html"></iframe>',
        signup_url="https://www.paypal.com/checkoutweb/signup?token=EC-TEST",
        proxy=None,
        timeout=1,
    ) is True


def test_paypal_browser_recaptcha_detection_is_disabled():
    card = _load_module("ctf_pay_card_recaptcha_ignore_test", "CTF-pay/card.py")

    class FakePage:
        pass

    assert card._paypal_recaptcha_visible(FakePage()) is False
