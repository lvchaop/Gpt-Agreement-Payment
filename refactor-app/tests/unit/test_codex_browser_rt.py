from __future__ import annotations

from refactor_app.plugins.openai_auth_protocol.codex_browser_rt import (
    _has_password_input,
    _phone_verification_failure,
    _submit_password_if_visible,
)


class _Button:
    def __init__(self) -> None:
        self.clicked = False

    def is_visible(self) -> bool:
        return True

    def evaluate(self, _script: str) -> None:
        self.clicked = True


class _Page:
    def __init__(self, button: _Button | None = None) -> None:
        self.button = button
        self.queries: list[str] = []

    def query_selector(self, selector: str):
        self.queries.append(selector)
        return self.button


def test_select_channel_returns_permanent_account_marker_code_without_clicking() -> None:
    page = _Page(_Button())

    failure = _phone_verification_failure(
        page,
        "https://auth.openai.com/phone-otp/select-channel",
    )

    assert failure == "phone_otp_select_channel"
    assert page.queries == []


def test_add_phone_continues_when_skip_control_is_available() -> None:
    button = _Button()
    page = _Page(button)

    failure = _phone_verification_failure(
        page,
        "https://auth.openai.com/add-phone",
    )

    assert failure == ""
    assert button.clicked is True


def test_add_phone_returns_separate_failure_when_it_cannot_be_skipped() -> None:
    page = _Page()

    failure = _phone_verification_failure(
        page,
        "https://auth.openai.com/add-phone",
    )

    assert failure == "add_phone_blocked"


def test_empty_password_is_not_submitted() -> None:
    page = _Page(_Button())

    assert _submit_password_if_visible(page, "") is False
    assert page.queries == []


def test_password_input_detection() -> None:
    page = _Page(_Button())

    assert _has_password_input(page) is True
    assert page.queries == ['input[type="password"]:visible']
