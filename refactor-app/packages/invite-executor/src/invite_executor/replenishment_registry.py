from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from uuid import uuid4

from pydantic import BaseModel, Field, SecretStr, ValidationError, field_validator

from invite_executor.replenishment_models import (
    CredentialType,
    ReplenishmentRegistration,
    SpaceReplenishmentConfig,
)


class ReplenishmentRegistryError(RuntimeError):
    pass


class ReplenishmentAdminRecord(BaseModel):
    admin_key: str = Field(min_length=1, max_length=320)
    email: str = Field(default="", max_length=320)
    user_id: str = Field(default="", max_length=200)
    cookie_header: SecretStr = SecretStr("")
    proxy_url: SecretStr = SecretStr("")
    updated_at: datetime

    @field_validator("admin_key", "email", "user_id", mode="before")
    @classmethod
    def strip_text(cls, value: object) -> str:
        return str(value or "").strip()

    @field_validator("cookie_header", "proxy_url", mode="before")
    @classmethod
    def strip_secret(cls, value: object) -> str:
        if isinstance(value, SecretStr):
            return value.get_secret_value().strip()
        return str(value or "").strip()


class ReplenishmentSpaceRecord(BaseModel):
    external_space_id: str = Field(min_length=1, max_length=200)
    name: str = Field(default="", max_length=320)
    enabled: bool = True
    credential_type: CredentialType
    seat_limit: int = Field(ge=1, le=1000)
    admin_key: str = Field(min_length=1, max_length=320)
    access_token: SecretStr = SecretStr("")
    updated_at: datetime

    @field_validator("external_space_id", "name", "admin_key", mode="before")
    @classmethod
    def strip_text(cls, value: object) -> str:
        return str(value or "").strip()

    @field_validator("access_token", mode="before")
    @classmethod
    def strip_secret(cls, value: object) -> str:
        if isinstance(value, SecretStr):
            return value.get_secret_value().strip()
        return str(value or "").strip()


@dataclass(frozen=True)
class ReplenishmentRegistrySnapshot:
    admins: tuple[ReplenishmentAdminRecord, ...]
    spaces: tuple[ReplenishmentSpaceRecord, ...]


class ReplenishmentRegistry:
    def __init__(self, path: str | Path) -> None:
        normalized_path = str(path or "").strip()
        if not normalized_path:
            raise ReplenishmentRegistryError("replenishment registry path is required")
        self._path = Path(normalized_path).expanduser()
        self._lock = Lock()
        self._admins: dict[str, ReplenishmentAdminRecord] = {}
        self._spaces: dict[str, ReplenishmentSpaceRecord] = {}
        self._load()

    @property
    def path(self) -> Path:
        return self._path

    def snapshot(self) -> ReplenishmentRegistrySnapshot:
        with self._lock:
            return ReplenishmentRegistrySnapshot(
                admins=tuple(
                    self._admins[key].model_copy(deep=True)
                    for key in sorted(self._admins)
                ),
                spaces=tuple(
                    self._spaces[key].model_copy(deep=True)
                    for key in sorted(self._spaces)
                ),
            )

    def resolved_spaces(self) -> tuple[SpaceReplenishmentConfig, ...]:
        with self._lock:
            return tuple(
                self._resolve_locked(self._spaces[key])
                for key in sorted(self._spaces)
            )

    def register_from_invitation(
        self,
        *,
        external_space_id: str,
        registration: ReplenishmentRegistration,
        access_token: str,
        cookie_header: str,
    ) -> SpaceReplenishmentConfig:
        now = datetime.now(UTC)
        with self._lock:
            previous_admins = dict(self._admins)
            previous_spaces = dict(self._spaces)
            existing_admin = self._admins.get(registration.admin_key)
            existing_space = self._spaces.get(str(external_space_id or "").strip())
            admin = ReplenishmentAdminRecord(
                admin_key=registration.admin_key,
                email=registration.admin_email or (existing_admin.email if existing_admin else ""),
                user_id=(
                    registration.admin_user_id
                    or (existing_admin.user_id if existing_admin else "")
                ),
                cookie_header=(
                    str(cookie_header or "").strip()
                    or (
                        existing_admin.cookie_header.get_secret_value()
                        if existing_admin
                        else ""
                    )
                ),
                proxy_url=(
                    registration.admin_proxy_url.get_secret_value()
                    or (
                        existing_admin.proxy_url.get_secret_value()
                        if existing_admin
                        else ""
                    )
                ),
                updated_at=now,
            )
            space = ReplenishmentSpaceRecord(
                external_space_id=external_space_id,
                name=registration.name,
                enabled=registration.enabled,
                credential_type=registration.credential_type,
                seat_limit=registration.seat_limit,
                admin_key=registration.admin_key,
                access_token=(
                    str(access_token or "").strip()
                    or (
                        existing_space.access_token.get_secret_value()
                        if existing_space
                        else ""
                    )
                ),
                updated_at=now,
            )
            resolved = self._resolve_records(space=space, admin=admin)
            previous_space = self._spaces.get(space.external_space_id)
            self._admins[admin.admin_key] = admin
            self._spaces[space.external_space_id] = space
            self._prune_unreferenced_admin_locked(
                previous_space.admin_key if previous_space is not None else ""
            )
            try:
                self._save_locked()
            except Exception:
                self._admins = previous_admins
                self._spaces = previous_spaces
                raise
            return resolved

    def remove_space(self, external_space_id: str) -> bool:
        space_id = str(external_space_id or "").strip()
        with self._lock:
            previous_admins = dict(self._admins)
            previous_spaces = dict(self._spaces)
            removed = self._spaces.pop(space_id, None)
            if removed is None:
                return False
            self._prune_unreferenced_admin_locked(removed.admin_key)
            try:
                self._save_locked()
            except Exception:
                self._admins = previous_admins
                self._spaces = previous_spaces
                raise
            return True

    def _resolve_locked(self, space: ReplenishmentSpaceRecord) -> SpaceReplenishmentConfig:
        admin = self._admins.get(space.admin_key)
        if admin is None:
            raise ReplenishmentRegistryError(
                f"space references missing administrator: {space.external_space_id}"
            )
        return self._resolve_records(space=space, admin=admin)

    @staticmethod
    def _resolve_records(
        *,
        space: ReplenishmentSpaceRecord,
        admin: ReplenishmentAdminRecord,
    ) -> SpaceReplenishmentConfig:
        return SpaceReplenishmentConfig(
            external_space_id=space.external_space_id,
            name=space.name,
            enabled=space.enabled,
            credential_type=space.credential_type,
            seat_limit=space.seat_limit,
            admin_key=admin.admin_key,
            admin_email=admin.email,
            admin_user_id=admin.user_id,
            admin_access_token=space.access_token,
            admin_cookie_header=admin.cookie_header,
            admin_proxy_url=admin.proxy_url,
        )

    def _prune_unreferenced_admin_locked(self, admin_key: str) -> None:
        if not admin_key:
            return
        if any(space.admin_key == admin_key for space in self._spaces.values()):
            return
        self._admins.pop(admin_key, None)

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or payload.get("version") != 1:
                raise ReplenishmentRegistryError("unsupported replenishment registry version")
            admins = payload.get("admins")
            spaces = payload.get("spaces")
            if not isinstance(admins, list) or not isinstance(spaces, list):
                raise ReplenishmentRegistryError("invalid replenishment registry structure")
            parsed_admins = {
                item.admin_key: item
                for item in (ReplenishmentAdminRecord.model_validate(row) for row in admins)
            }
            legacy_admin_tokens = {
                str(row.get("admin_key") or "").strip(): str(
                    row.get("access_token") or ""
                ).strip()
                for row in admins
                if isinstance(row, dict)
            }
            parsed_space_rows: list[ReplenishmentSpaceRecord] = []
            for row in spaces:
                if not isinstance(row, dict):
                    raise ReplenishmentRegistryError("invalid replenishment space record")
                migrated_row = dict(row)
                if not str(migrated_row.get("access_token") or "").strip():
                    migrated_row["access_token"] = legacy_admin_tokens.get(
                        str(migrated_row.get("admin_key") or "").strip(),
                        "",
                    )
                parsed_space_rows.append(
                    ReplenishmentSpaceRecord.model_validate(migrated_row)
                )
            parsed_spaces = {item.external_space_id: item for item in parsed_space_rows}
            if len(parsed_admins) != len(admins):
                raise ReplenishmentRegistryError("duplicate administrator key in registry")
            if len(parsed_spaces) != len(spaces):
                raise ReplenishmentRegistryError("duplicate external_space_id in registry")
            missing_admins = sorted(
                {space.admin_key for space in parsed_spaces.values()} - set(parsed_admins)
            )
            if missing_admins:
                raise ReplenishmentRegistryError(
                    "registry spaces reference missing administrators: "
                    + ", ".join(missing_admins)
                )
        except ReplenishmentRegistryError:
            raise
        except (OSError, json.JSONDecodeError, ValidationError) as exc:
            raise ReplenishmentRegistryError(
                f"failed to load replenishment registry: {type(exc).__name__}: {exc}"
            ) from exc
        self._admins = parsed_admins
        self._spaces = parsed_spaces

    def _save_locked(self) -> None:
        parent = self._path.parent
        parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "admins": [
                {
                    "admin_key": admin.admin_key,
                    "email": admin.email,
                    "user_id": admin.user_id,
                    "cookie_header": admin.cookie_header.get_secret_value(),
                    "proxy_url": admin.proxy_url.get_secret_value(),
                    "updated_at": admin.updated_at.isoformat(),
                }
                for admin in sorted(self._admins.values(), key=lambda item: item.admin_key)
            ],
            "spaces": [
                {
                    "external_space_id": space.external_space_id,
                    "name": space.name,
                    "enabled": space.enabled,
                    "credential_type": space.credential_type,
                    "seat_limit": space.seat_limit,
                    "admin_key": space.admin_key,
                    "access_token": space.access_token.get_secret_value(),
                    "updated_at": space.updated_at.isoformat(),
                }
                for space in sorted(
                    self._spaces.values(), key=lambda item: item.external_space_id
                )
            ],
        }
        temporary = parent / f".{self._path.name}.{os.getpid()}.{uuid4().hex}.tmp"
        try:
            with temporary.open("x", encoding="utf-8") as handle:
                os.chmod(temporary, 0o600)
                json.dump(payload, handle, ensure_ascii=True, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self._path)
            os.chmod(self._path, 0o600)
        except OSError as exc:
            raise ReplenishmentRegistryError(
                f"failed to save replenishment registry: {type(exc).__name__}: {exc}"
            ) from exc
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
