from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
import re

from refactor_app.plugins.contracts import DownstreamCodexPayload, DownstreamPushResult
from refactor_app.plugins.downstream_sub2api.client import build_sub2api_import_payload


class LocalSub2ApiClientError(RuntimeError):
    pass


@dataclass(frozen=True)
class LocalSub2ApiClientConfig:
    output_dir: str
    update_existing: bool = False

    def effective_output_dir(self) -> Path:
        value = str(self.output_dir or "").strip()
        if value:
            return Path(value).expanduser()
        return Path.cwd() / "runtime" / "local-sub2api"


class LocalSub2ApiClient:
    def __init__(self, config: LocalSub2ApiClientConfig) -> None:
        self._config = config

    def push_codex_credential(self, payload: DownstreamCodexPayload) -> DownstreamPushResult:
        output_dir = self._config.effective_output_dir()
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            body = build_sub2api_import_payload(
                payload,
                update_existing=self._config.update_existing,
            )
            body["proxies"] = []
            path = output_dir / _local_sub2api_filename(payload)
            path.write_text(
                json.dumps(body, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            return DownstreamPushResult(
                pushed=False,
                error_code=type(exc).__name__[:200],
                error_message=str(exc)[:1000],
            )
        return DownstreamPushResult(
            pushed=True,
            downstream_external_id=str(path.resolve()),
            raw={"file_path": str(path.resolve())},
        )


def _local_sub2api_filename(payload: DownstreamCodexPayload) -> str:
    ts = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    credential_key = _safe_filename(payload.account_id or payload.downstream_chatgpt_account_id)
    email = _safe_filename(payload.email)
    return f"{ts}_{credential_key}_{email}.sub2api.json"


def _safe_filename(value: str) -> str:
    text = str(value or "").strip()
    text = re.sub(r"[^A-Za-z0-9._-]+", "-", text)
    text = text.strip(".-_")
    return text[:120] or "unknown"
