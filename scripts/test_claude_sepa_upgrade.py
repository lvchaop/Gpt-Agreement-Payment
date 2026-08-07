from __future__ import annotations

import importlib.util
import hashlib
import json
import sys
import threading
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest


SCRIPT = Path(__file__).with_name("claude_sepa_upgrade.py")
SPEC = importlib.util.spec_from_file_location("claude_sepa_upgrade", SCRIPT)
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = mod
SPEC.loader.exec_module(mod)


def test_magic_link_client_is_read_only_and_uses_claude_regex() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "success": True,
                "data": {"verification_code": "https://claude.ai/magic-link#abc123"},
            },
        )

    client = mod.ReadOnlyMagicLinkClient(
        base_url="https://mail.example.test",
        api_key="secret",
        timeout_s=2,
        poll_interval_s=0.5,
        client=httpx.Client(
            base_url="https://mail.example.test",
            transport=httpx.MockTransport(handler),
        ),
    )

    link = client.wait_for_magic_link(
        email="person@example.test",
        issued_after=1_000,
        timeout_s=1,
    )

    assert link == "https://claude.ai/magic-link#abc123"
    assert len(requests) == 1
    assert requests[0].method == "GET"
    assert requests[0].url.path == "/api/external/verification-code"
    assert requests[0].url.params["email"] == "person@example.test"
    assert requests[0].url.params["code_regex"] == mod.MAGIC_LINK_REGEX
    assert requests[0].url.params["code_source"] == "all"


@pytest.mark.parametrize(
    "value",
    [
        "http://claude.ai/magic-link#abc",
        "https://example.test/magic-link#abc",
        "https://claude.ai/magic-link",
        "https://claude.ai/not-magic#abc",
    ],
)
def test_magic_link_validation_rejects_other_urls(value: str) -> None:
    with pytest.raises(mod.MailLookupError):
        mod.validate_magic_link(value)


def test_magic_link_validation_accepts_uppercase_path_from_mail_api() -> None:
    link = "https://claude.ai/MAGIC-LINK#abc123"

    assert mod.validate_magic_link(link) == link


def test_magic_link_payload_prefers_original_case_link_array() -> None:
    original = "https://claude.ai/magic-link#AbCdEf123456"
    formatted = "https://claude.ai/MAGIC-LINK#ABCDEF123456"

    selected = mod.magic_link_from_payload(
        {
            "success": True,
            "data": {
                "links": [
                    "https://claude.ai/images/claude_logo_full.png",
                    original,
                ],
                "verification_code": formatted,
            },
        }
    )

    assert selected == original


def test_mail_received_timestamp_parses_imap_date() -> None:
    value = "Sun, 26 Jul 2026 15:51:43 +0000 (UTC)"

    assert mod.mail_received_timestamp(value) == datetime(
        2026, 7, 26, 15, 51, 43, tzinfo=mod.timezone.utc
    ).timestamp()


def test_load_inputs_preserves_email_order_and_randomly_selects_iban(tmp_path: Path) -> None:
    emails = tmp_path / "emails.txt"
    ibans = tmp_path / "ibans.txt"
    extension = tmp_path / "extension"
    extension.mkdir()
    (extension / "manifest.json").write_text("{}", encoding="utf-8")
    emails.write_text("first@example.test\nsecond@example.test\n", encoding="utf-8")
    ibans.write_text(
        "DE89370400440532013000\nDE12500105170648489890\n",
        encoding="utf-8",
    )
    config = mod.UpgradeConfig(
        emails_file=emails,
        ibans_file=ibans,
        billing=mod.BillingProfile(
            full_name="Test Person",
            country="DE",
            line1="Teststrasse 1",
            line2="",
            postal_code="10115",
            city="Berlin",
        ),
        extension_path=extension,
        output_dir=tmp_path / "output",
        mail_base_url="https://mail.example.test",
        mail_api_key="secret",
        proxy=mod.BackboneProxyConfig(
            country="DE",
            database_url="postgresql://example.test/db",
        ),
    )

    accounts = mod.load_account_inputs(config, randbelow=lambda _size: 0)

    assert [(item.index, item.email, item.iban) for item in accounts] == [
        (1, "first@example.test", "DE89370400440532013000"),
        (2, "second@example.test", "DE89370400440532013000"),
    ]


def test_iban_retry_candidates_start_with_selected_and_do_not_repeat(
    tmp_path: Path,
) -> None:
    ibans = tmp_path / "ibans.txt"
    ibans.write_text(
        "DE89370400440532013000\nDE12500105170648489890\n",
        encoding="utf-8",
    )

    candidates = mod.iban_retry_candidates(
        ibans,
        "DE12 5001 0517 0648 4898 90",
        shuffle=lambda _items: None,
    )

    assert candidates == [
        "DE12500105170648489890",
        "DE89370400440532013000",
    ]


def test_load_inputs_randomly_selects_name_address_and_iban(tmp_path: Path) -> None:
    emails = tmp_path / "emails.txt"
    ibans = tmp_path / "ibans.txt"
    addresses = tmp_path / "addresses.txt"
    names = tmp_path / "names.txt"
    extension = tmp_path / "extension"
    extension.mkdir()
    (extension / "manifest.json").write_text("{}", encoding="utf-8")
    emails.write_text("first@example.test\n", encoding="utf-8")
    ibans.write_text(
        "DE89370400440532013000\nDE12500105170648489890\n",
        encoding="utf-8",
    )
    addresses.write_text(
        "Teststrasse 1, 10115 Berlin, Germany\n"
        "Beispielweg 2,10, 20095 Hamburg, Germany\n",
        encoding="utf-8",
    )
    names.write_text("Anna Müller\nFelix Schneider\n", encoding="utf-8")
    config = mod.UpgradeConfig(
        emails_file=emails,
        ibans_file=ibans,
        billing=mod.BillingProfile(
            full_name="",
            country="DE",
            line1="",
            line2="",
            postal_code="",
            city="",
        ),
        extension_path=extension,
        output_dir=tmp_path / "output",
        mail_base_url="https://mail.example.test",
        mail_api_key="secret",
        proxy=mod.BackboneProxyConfig(country="DE", database_url="unused"),
        addresses_file=addresses,
        names_file=names,
    )
    selections = iter((1, 1, 1))

    accounts = mod.load_account_inputs(
        config,
        randbelow=lambda _size: next(selections),
    )

    assert len(accounts) == 1
    assert accounts[0].email == "first@example.test"
    assert accounts[0].iban == "DE12500105170648489890"
    assert accounts[0].billing == mod.BillingProfile(
        full_name="Felix Schneider",
        country="DE",
        line1="Beispielweg 2, 10",
        line2="",
        postal_code="20095",
        city="Hamburg",
    )


def test_success_record_does_not_store_iban_or_magic_link(tmp_path: Path) -> None:
    recorder = mod.JsonlRecorder(tmp_path)
    recorder.success(email="person@example.test")

    payload = json.loads((tmp_path / "success.jsonl").read_text(encoding="utf-8"))

    assert payload["email"] == "person@example.test"
    assert payload["plan"] == "claude_max_20x_monthly"
    assert "iban" not in payload
    assert "magic_link" not in payload


def test_prepare_extension_keeps_protected_javascript_unchanged(tmp_path: Path) -> None:
    source = tmp_path / "source-extension"
    target = tmp_path / "derived-extension"
    source.mkdir()
    (source / "manifest.json").write_text(
        json.dumps(
            {
                "manifest_version": 3,
                "name": "Claude SEPA Helper",
                "version": "1.0.8",
                "permissions": ["activeTab", "scripting", "storage"],
            }
        ),
        encoding="utf-8",
    )
    scripts = {
        "claude-sepa.js": b"protected-content-script",
        "popup.js": b"protected-popup-script",
        "status-only.js": b"protected-status-script",
    }
    for name, content in scripts.items():
        (source / name).write_bytes(content)

    mod.prepare_extension(source, target)

    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["host_permissions"] == ["https://claude.ai/*"]
    assert manifest["background"] == {
        "service_worker": "codex-automation-background.js"
    }
    for name, content in scripts.items():
        assert hashlib.sha256((target / name).read_bytes()).digest() == hashlib.sha256(
            content
        ).digest()


def test_uncertain_payment_is_cleared_only_after_success(tmp_path: Path) -> None:
    recorder = mod.JsonlRecorder(tmp_path)
    recorder.event(
        email="person@example.test",
        stage="payment",
        status="submitting",
    )

    assert recorder.uncertain_payment_emails() == {"person@example.test"}

    recorder.event(
        email="person@example.test",
        stage="payment",
        status="failed",
    )
    assert recorder.uncertain_payment_emails() == set()

    recorder.event(
        email="person@example.test",
        stage="payment",
        status="submitting",
    )

    recorder.event(
        email="person@example.test",
        stage="workflow",
        status="failed",
    )
    assert recorder.uncertain_payment_emails() == {"person@example.test"}

    recorder.event(
        email="person@example.test",
        stage="workflow",
        status="succeeded",
    )
    assert recorder.uncertain_payment_emails() == set()


def test_recorder_tracks_terminal_failed_emails(tmp_path: Path) -> None:
    recorder = mod.JsonlRecorder(tmp_path)

    recorder.failure(email="person@example.test", reason="account_banned")

    assert recorder.failed_emails() == {"person@example.test"}
    payload = json.loads(recorder.failed_path.read_text().splitlines()[0])
    assert payload["reason"] == "account_banned"


def test_random_birth_date_uses_exact_25_to_38_age_boundaries() -> None:
    today = date(2026, 7, 26)

    youngest = mod.random_birth_date(today=today, randbelow=lambda _size: 0)
    oldest = mod.random_birth_date(today=today, randbelow=lambda size: size - 1)

    youngest_date = datetime.strptime(youngest, "%m/%d/%Y").date()
    oldest_date = datetime.strptime(oldest, "%m/%d/%Y").date()
    assert mod.age_on_date(youngest_date, today=today) == 25
    assert mod.age_on_date(oldest_date, today=today) == 38


def test_random_birth_date_handles_leap_day_reference() -> None:
    today = date(2024, 2, 29)
    values = iter((13, 0))

    generated = mod.random_birth_date(today=today, randbelow=lambda _size: next(values))

    generated_date = datetime.strptime(generated, "%m/%d/%Y").date()
    assert mod.age_on_date(generated_date, today=today) == 38


def test_birth_date_is_split_for_react_date_picker_inputs() -> None:
    assert mod.birth_date_parts("07/26/1991") == ("26", "7", "1991")


def test_backbone_pool_uses_de_and_unique_endpoint_and_exit_ip() -> None:
    config = mod.BackboneProxyConfig(
        country="DE",
        database_url="",
        gateway_host="p.webshare.io",
        gateway_port=80,
        scan_concurrency=1,
    )
    observed_urls: list[str] = []

    def probe(proxy_url: str) -> tuple[str, str, str]:
        observed_urls.append(proxy_url)
        username = mod.playwright_proxy(proxy_url)["username"]
        endpoint = int(username.rsplit("-", 1)[1])
        ip_by_endpoint = {
            1: "192.0.2.1",
            2: "192.0.2.1",
            3: "192.0.2.3",
        }
        ip = ip_by_endpoint[endpoint]
        return ip, ip, "DE"

    pool = mod.WebshareBackboneProxyPool(
        config,
        inventory_loader=lambda: ("ibtvqcnm", "password/with:chars", [1, 2, 3]),
        probe=probe,
        shuffle=lambda _endpoints: None,
    )

    assignments = pool.allocate(2)

    assert [assignment.endpoint for assignment in assignments] == [1, 3]
    assert [assignment.exit_ip for assignment in assignments] == ["192.0.2.1", "192.0.2.3"]
    assert all(assignment.country == "DE" for assignment in assignments)
    assert mod.playwright_proxy(assignments[0].proxy_url) == {
        "server": "http://p.webshare.io:80",
        "username": "ibtvqcnm-DE-1",
        "password": "password/with:chars",
    }
    assert len(observed_urls) == 3


def test_backbone_pool_rejects_rotating_or_non_de_exit() -> None:
    config = mod.BackboneProxyConfig(
        country="DE",
        database_url="",
        scan_concurrency=1,
    )
    observations = iter(
        [
            ("192.0.2.1", "192.0.2.2", "DE"),
            ("192.0.2.3", "192.0.2.3", "GE"),
        ]
    )
    pool = mod.WebshareBackboneProxyPool(
        config,
        inventory_loader=lambda: ("ibtvqcnm", "password", [1, 2]),
        probe=lambda _proxy_url: next(observations),
        shuffle=lambda _endpoints: None,
    )

    with pytest.raises(mod.ProxyPoolError, match="insufficient verified DE Backbone exits"):
        pool.allocate(1)


def test_backbone_pool_never_reuses_endpoint_or_exit_across_allocations() -> None:
    config = mod.BackboneProxyConfig(
        country="DE",
        database_url="",
        scan_concurrency=1,
    )
    pool = mod.WebshareBackboneProxyPool(
        config,
        inventory_loader=lambda: ("ibtvqcnm", "password", [1, 2]),
        probe=lambda proxy_url: (
            f"192.0.2.{mod.playwright_proxy(proxy_url)['username'].rsplit('-', 1)[1]}",
            f"192.0.2.{mod.playwright_proxy(proxy_url)['username'].rsplit('-', 1)[1]}",
            "DE",
        ),
        shuffle=lambda _endpoints: None,
    )

    first = pool.allocate(1)[0]
    second = pool.allocate(1)[0]

    assert first.endpoint == 1
    assert second.endpoint == 2
    assert first.exit_ip != second.exit_ip


def test_backbone_username_normalization() -> None:
    assert mod._backbone_base_username("ibtvqcnm-1") == "ibtvqcnm"
    assert mod._backbone_base_username("ibtvqcnm-GB-1") == "ibtvqcnm"
    assert mod._backbone_base_username("ibtvqcnm") == "ibtvqcnm"


def test_chromium_fingerprint_options_are_german_and_isolated(tmp_path: Path) -> None:
    assignment = mod.BackboneProxyAssignment(
        endpoint=17,
        proxy_url="http://user-DE-17:password@p.webshare.io:80",
        exit_ip="192.0.2.17",
        country="DE",
    )
    profile = tmp_path / "profile-17"
    extension = tmp_path / "extension"

    options = mod.chromium_fingerprint_launch_options(
        config=SimpleNamespace(headless=False, browser_executable=None),
        proxy_assignment=assignment,
        profile_dir=profile,
        extension_dir=extension,
    )

    assert options["user_data_dir"] == str(profile)
    assert options["proxy"]["username"] == "user-DE-17"
    assert options["locale"] == "en-DE"
    assert options["timezone_id"] == "Europe/Berlin"
    assert options["ignore_default_args"] == ["--enable-automation"]
    assert "--disable-blink-features=AutomationControlled" in options["args"]
    assert f"--load-extension={extension}" in options["args"]


def test_camoufox_fingerprint_uses_verified_exit_for_geoip(tmp_path: Path) -> None:
    assignment = mod.BackboneProxyAssignment(
        endpoint=17,
        proxy_url="http://user-DE-17:password@p.webshare.io:80",
        exit_ip="192.0.2.17",
        country="DE",
    )

    options = mod.camoufox_fingerprint_launch_options(
        config=SimpleNamespace(headless=False),
        proxy_assignment=assignment,
        profile_dir=tmp_path / "profile-17",
    )

    assert options["humanize"] is True
    assert options["persistent_context"] is True
    assert options["os"] == "windows"
    assert options["geoip"] == assignment.exit_ip
    assert options["locale"] == "de-DE"
    assert options["proxy"]["username"] == "user-DE-17"


def test_direct_script_controller_injects_original_file(tmp_path: Path) -> None:
    script = tmp_path / "claude-sepa.js"
    script.write_text("window.__sepaProbe = true;", encoding="utf-8")
    calls: list[tuple[str, str]] = []

    class FakePage:
        def add_script_tag(self, *, path: str) -> None:
            calls.append(("script", path))

        def bring_to_front(self) -> None:
            calls.append(("front", ""))

    assert mod.DirectScriptController(tmp_path).inject(FakePage(), script.name) is True
    assert calls == [("script", str(script)), ("front", "")]


def test_full_address_query_includes_postal_code_and_city() -> None:
    profile = mod.BillingProfile(
        full_name="Christoph Graf",
        country="DE",
        line1="Antoniterstraße 14-16",
        line2="",
        postal_code="50667",
        city="Köln",
    )

    assert mod.full_address_query(profile) == (
        "Antoniterstraße 14-16, 50667 Köln, Germany"
    )


def test_stripe_billing_source_attributes_match_field_selectors() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    for selector in (
        'input[name="name"]',
        'select[name="country"]',
        'input[name="addressLine1"]',
        'input[name="postalCode"]',
        'input[name="locality"]',
        'input[autocomplete$=" name"]',
        'input[autocomplete$=" address-line1"]',
    ):
        assert selector in source

    assert "Vollständiger Name" in source
    assert "Land oder Region" in source
    assert r"^Adresse$" in source


def test_sepa_fields_are_scoped_to_plugin_stripe_containers() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert '#csh-billing-address iframe[src*="elements-inner-address"]' in source
    assert '#csh-billing-address iframe[src*="autocomplete-suggestions"]' in source
    assert '#csh-payment-element iframe[src*="elements-inner-payment"]' in source
    assert 'page.locator("#csh-consent")' in source
    assert 'page.locator("#csh-pay")' in source


def test_plugin_address_has_bounded_retries_and_post_selection_check() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "for attempt in range(1, 4):" in source
    assert "timeout_s=6" in source
    assert "_wait_for_plugin_address" in source
    assert "plugin Google address suggestion was not selected after 3 attempts" in source


def test_login_navigation_errors_are_retried() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "for attempt in range(1, 4):" in source
    assert "navigation_error =" in source
    assert "if page.is_closed():" in source


def test_exhausted_iban_candidates_trigger_account_replacement() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert 'raise AccountTerminalError("all test IBAN candidates were rejected")' in source


def test_check_checkbox_forces_hidden_input_without_long_retry() -> None:
    calls: list[str] = []

    class FakeCheckbox:
        checked = False

        def is_checked(self) -> bool:
            return self.checked

        def evaluate(self, script: str) -> None:
            calls.append(script)
            self.checked = True

    mod._check_checkbox(FakeCheckbox())

    assert len(calls) == 1
    assert "label" in calls[0]


def test_fill_exact_rejects_truncated_value() -> None:
    class FakeField:
        value = ""

        def click(self) -> None:
            pass

        def fill(self, value: str) -> None:
            self.value = value[:5]

        def input_value(self) -> str:
            return self.value

    with pytest.raises(mod.BrowserFlowError, match="input value mismatch"):
        mod._fill_exact(FakeField(), "complete@example.test")


def test_fill_iban_exact_accepts_stripe_space_formatting() -> None:
    class FakeIbanField:
        value = ""

        def click(self) -> None:
            pass

        def fill(self, value: str) -> None:
            self.value = " ".join(value[index : index + 4] for index in range(0, len(value), 4))

        def input_value(self) -> str:
            return self.value

    field = FakeIbanField()

    mod._fill_iban_exact(field, "DE89370400440532013000")

    assert field.input_value() == "DE89 3704 0044 0532 0130 00"


def test_button_following_input_uses_dom_position_not_translated_text() -> None:
    class FakeButton:
        def count(self) -> int:
            return 1

        def nth(self, index: int) -> object:
            assert index == 0
            return self

        def is_visible(self) -> bool:
            return True

    button = FakeButton()

    class FakeField:
        def locator(self, selector: str) -> object:
            assert selector == "xpath=following::button[1]"
            return button

    assert mod._button_following_input(FakeField()) is button


def test_max_checkout_rejects_login_redirect() -> None:
    class EmptyLocator:
        def count(self) -> int:
            return 0

        def inner_text(self) -> str:
            return ""

    page = SimpleNamespace(
        url="https://claude.ai/login?returnTo=%2Fupgrade%2Fmax",
        locator=lambda selector: EmptyLocator(),
    )
    with pytest.raises(mod.BrowserFlowError, match="without authorization"):
        mod._wait_for_max_checkout(page, timeout_s=0.1)


def test_phone_verification_is_terminal_account_state() -> None:
    class PhoneLocator:
        def count(self) -> int:
            return 1

        def nth(self, index: int) -> object:
            assert index == 0
            return self

        def is_visible(self) -> bool:
            return True

    page = SimpleNamespace(locator=lambda _selector: PhoneLocator())

    with pytest.raises(mod.AccountTerminalError, match="phone verification"):
        mod._raise_if_terminal_account_state(page)


def test_magic_link_accepts_onboarding_dom_before_url_changes() -> None:
    class FakeLocator:
        def count(self) -> int:
            return 1

        def nth(self, index: int) -> object:
            assert index == 0
            return self

        def is_visible(self) -> bool:
            return True

    page = SimpleNamespace(
        url="https://claude.ai/magic-link#token",
        locator=lambda _selector: FakeLocator(),
    )

    mod._wait_for_authenticated_page(page, timeout_s=0.1)


def test_run_starts_multiple_browser_flows_concurrently(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    emails = tmp_path / "emails.txt"
    ibans = tmp_path / "ibans.txt"
    extension = tmp_path / "extension"
    extension.mkdir()
    (extension / "manifest.json").write_text("{}", encoding="utf-8")
    emails.write_text("first@example.test\nsecond@example.test\n", encoding="utf-8")
    ibans.write_text(
        "DE89370400440532013000\nDE12500105170648489890\n",
        encoding="utf-8",
    )
    config = mod.UpgradeConfig(
        emails_file=emails,
        ibans_file=ibans,
        billing=mod.BillingProfile(
            full_name="Test Person",
            country="DE",
            line1="Teststrasse 1",
            line2="",
            postal_code="10115",
            city="Berlin",
        ),
        extension_path=extension,
        output_dir=tmp_path / "output",
        mail_base_url="https://mail.example.test",
        mail_api_key="secret",
        proxy=mod.BackboneProxyConfig(country="DE", database_url="unused"),
        browser_concurrency=2,
    )
    assignments = [
        mod.BackboneProxyAssignment(
            endpoint=index,
            proxy_url=f"http://user-DE-{index}:password@p.webshare.io:80",
            exit_ip=f"192.0.2.{index}",
            country="DE",
        )
        for index in (1, 2)
    ]
    barrier = threading.Barrier(2)
    entered: list[str] = []
    entered_lock = threading.Lock()

    class FakeProxyPool:
        def __init__(self, _config: object) -> None:
            pass

        def allocate(self, required_count: int) -> list[object]:
            assert required_count == 2
            return assignments

    class FakeMailClient:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def close(self) -> None:
            pass

    class FakeBrowserFlow:
        def __init__(
            self,
            _config: object,
            _artifacts_dir: Path,
                _proxy_assignment: object,
                *,
                on_payment_submit: object,
                on_payment_failure: object,
            ) -> None:
                assert on_payment_submit is not None
                assert on_payment_failure is not None

        def run(self, account: object, _mail_client: object) -> bool:
            with entered_lock:
                entered.append(account.email)
            barrier.wait(timeout=2)
            return True

    monkeypatch.setattr(mod, "WebshareBackboneProxyPool", FakeProxyPool)
    monkeypatch.setattr(mod, "ReadOnlyMagicLinkClient", FakeMailClient)
    monkeypatch.setattr(mod, "ClaudeSepaBrowserFlow", FakeBrowserFlow)

    result = mod.run(config)

    assert result == 0
    assert set(entered) == {"first@example.test", "second@example.test"}
    success_rows = [
        json.loads(line)
        for line in (config.output_dir / "success.jsonl").read_text().splitlines()
    ]
    assert {row["email"] for row in success_rows} == set(entered)
    for line in (config.output_dir / "events.jsonl").read_text().splitlines():
        assert isinstance(json.loads(line), dict)
