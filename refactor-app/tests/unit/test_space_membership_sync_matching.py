from types import SimpleNamespace

from refactor_app.application.workflows.space_membership_invite_sync import (
    _account_by_openai_user_id,
    _match_member_account,
)


class _ScalarRows:
    def __init__(self, rows: list[SimpleNamespace]) -> None:
        self._rows = rows

    def all(self) -> list[SimpleNamespace]:
        return self._rows


class _Session:
    def __init__(self, rows: list[SimpleNamespace]) -> None:
        self._rows = rows

    def scalars(self, _statement: object) -> _ScalarRows:
        return _ScalarRows(self._rows)


def test_account_by_openai_user_id_indexes_bare_and_workspace_suffixed_ids() -> None:
    account = SimpleNamespace(
        id="account-1",
        openai_user_id="user-ON0K8PUL5vaYOUqqf1ejeZkX__4fa7a76b-fe3b-46a6-ae44-5c581077c899",
    )

    result = _account_by_openai_user_id(session=_Session([account]))  # type: ignore[arg-type]

    assert result["user-ON0K8PUL5vaYOUqqf1ejeZkX"] is account
    assert (
        result["user-ON0K8PUL5vaYOUqqf1ejeZkX__4fa7a76b-fe3b-46a6-ae44-5c581077c899"]
        is account
    )


def test_match_member_account_uses_remote_user_id_against_normalized_local_openai_user_id() -> None:
    account = SimpleNamespace(id="account-1")
    member = {
        "id": "user-ON0K8PUL5vaYOUqqf1ejeZkX",
        "account_user_id": "user-ON0K8PUL5vaYOUqqf1ejeZkX__4fa7a76b-fe3b-46a6-ae44-5c581077c899",
        "email": None,
        "verified_email": None,
    }

    matched = _match_member_account(
        member=member,
        account_by_email={},
        account_by_openai_user_id={
            "user-ON0K8PUL5vaYOUqqf1ejeZkX": account,
            "user-ON0K8PUL5vaYOUqqf1ejeZkX__4fa7a76b-fe3b-46a6-ae44-5c581077c899": account,
        },
    )

    assert matched is account
