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


def _ratenn_sample():
    return {
        "name": "丸尾 博幸",
        "name_hiragana": "まるお ひろゆき",
        "name_katakana": "マルオ ヒロユキ",
        "birth": "1968-06-08",
        "address": {
            "full_address": "愛知県春日井市勝川町西2-2-19",
            "country": "Japan",
            "prefecture": "愛知県",
            "city": "春日井市",
            "postal_code": "459-6477",
        },
    }


def test_ratenn_jp_address_uses_kanji_and_katakana(monkeypatch):
    card = _load_module("ctf_pay_card_jp_test", "CTF-pay/card.py")
    monkeypatch.setattr(card, "_log", lambda *_args, **_kwargs: None)

    class Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return _ratenn_sample()

    seen = {}

    def fake_get(url, **kwargs):
        seen["url"] = url
        seen["kwargs"] = kwargs
        return Resp()

    monkeypatch.setattr(card.requests, "get", fake_get)

    address = card._paypal_fetch_ratenn_jp_address({"country": "JP"})

    assert seen["url"] == "https://hant.ratenn.com/jp-address/generate-address"
    assert address["country"] == "JP"
    assert address["state"] == "愛知県"
    assert address["city"] == "春日井市勝川町西"
    assert address["line1"] == "2-2-19"
    assert address["postal_code"] == "459-6477"
    assert address["first_name"] == "丸尾"
    assert address["last_name"] == "博幸"
    assert address["first_name_hiragana"] == "まるお"
    assert address["last_name_hiragana"] == "ひろゆき"
    assert address["country_specific_first_name"] == "マルオ"
    assert address["country_specific_last_name"] == "ヒロユキ"
    assert address["date_of_birth"] == {"year": "1968", "month": "06", "day": "08"}


def test_signup_variables_match_jp_har_shape():
    signup = _load_module("paypal_plus_signup_jp_test", "CTF-reg/paypal_plus/signup.py")
    address = {
        "country": "JP",
        "state": "愛知県",
        "city": "春日井市勝川町西",
        "line1": "2-2-19",
        "postal_code": "459-6477",
        "first_name": "丸尾",
        "last_name": "博幸",
        "first_name_hiragana": "まるお",
        "last_name_hiragana": "ひろゆき",
        "first_name_katakana": "マルオ",
        "last_name_katakana": "ヒロユキ",
        "country_specific_first_name": "マルオ",
        "country_specific_last_name": "ヒロユキ",
        "nationality": "JP",
        "date_of_birth": {"year": "1968", "month": "06", "day": "08"},
        "autoCompleteType": "MANUAL",
        "isUserModified": True,
        "shipping_address": {
            "country": "JP",
            "line1": "",
            "city": "",
            "state": "",
            "postal_code": "",
            "autoCompleteType": "MANUAL",
            "isUserModified": False,
        },
    }
    persona = signup.Persona(
        first_name="丸尾",
        last_name="博幸",
        email="buyer@example.test",
        password="passw0rd!",
        line1="fallback",
        city="fallback",
        state="fallback",
        postal_code="00000",
        country="JP",
    )

    variables = signup._signup_variables(
        persona=persona,
        ec_token="EC-test",
        phone_e164="+817012345678",
        locale_country="JP",
        locale_lang="ja",
        content_identifier="JP:ja:d75a1bdbc6baa8ebe00aed449566be84:compliance.signupTerms",
        signup_card={
            "cardNumber": "4111111111111111",
            "expirationDate": "08/2030",
            "securityCode": "123",
            "type": "VISA",
        },
        signup_billing_address=address,
    )

    assert variables["country"] == "JP"
    assert variables["firstName"] == "丸尾"
    assert variables["lastName"] == "博幸"
    assert variables["nationality"] == "JP"
    assert variables["dateOfBirth"] == {"year": "1968", "month": "06", "day": "08"}
    assert variables["countrySpecificFirstName"] == "マルオ"
    assert variables["countrySpecificLastName"] == "ヒロユキ"
    assert variables["phone"] == {"countryCode": "81", "number": "7012345678", "type": "MOBILE"}
    assert variables["billingAddress"]["country"] == "JP"
    assert variables["billingAddress"]["state"] == "愛知県"
    assert variables["billingAddress"]["city"] == "春日井市勝川町西"
    assert variables["billingAddress"]["line1"] == "2-2-19"
    assert variables["billingAddress"]["postalCode"] == "459-6477"
    assert variables["billingAddress"]["accountQuality"] == {
        "autoCompleteType": "MANUAL",
        "isUserModified": True,
    }
    assert variables["shippingAddress"]["country"] == "JP"
    assert variables["shippingAddress"]["state"] == ""
    assert variables["shippingAddress"]["postalCode"] == ""


def test_paypal_card_type_mastercard_matches_graphql_enum():
    card = _load_module("ctf_pay_card_mastercard_test", "CTF-pay/card.py")

    assert card._paypal_card_type("5555555555554444") == "MASTER_CARD"
    assert card._paypal_card_type("2223000048400011") == "MASTER_CARD"


def test_signup_variables_normalize_mastercard_alias():
    signup = _load_module("paypal_plus_signup_mastercard_test", "CTF-reg/paypal_plus/signup.py")
    persona = signup.Persona(
        first_name="James",
        last_name="Smith",
        email="buyer@example.test",
        password="passw0rd!",
        line1="1 Main St",
        city="New York",
        state="NY",
        postal_code="10001",
        country="US",
    )

    variables = signup._signup_variables(
        persona=persona,
        ec_token="EC-test",
        phone_e164="+12025550123",
        locale_country="US",
        locale_lang="en",
        signup_card={
            "cardNumber": "5555555555554444",
            "expirationDate": "12/2029",
            "securityCode": "123",
            "type": "MASTERCARD",
        },
    )

    assert variables["card"]["type"] == "MASTER_CARD"


def test_gql_locale_follows_jp_signup_url():
    signup = _load_module("paypal_plus_signup_locale_test", "CTF-reg/paypal_plus/signup.py")

    country, lang = signup._gql_locale_parts(
        {"countryCodeAsString": "JP"},
        "https://www.paypal.com/checkoutweb/signup?country.x=JP&locale.x=ja_JP&token=EC-test",
    )

    assert (country, lang) == ("JP", "ja")
    assert signup._accept_language_header(country, lang) == "ja-JP,ja;q=0.9,en;q=0.8"
    assert signup._extract_content_identifier("", "JP", "ja") == (
        "JP:ja:d75a1bdbc6baa8ebe00aed449566be84:compliance.signupTerms"
    )
