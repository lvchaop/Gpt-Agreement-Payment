"""Identity generation for the portal protocol registration lane."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import string
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

try:
    import fcntl
except ImportError:  # pragma: no cover - non-Unix fallback
    fcntl = None


USERNAME_LETTERS = string.ascii_lowercase
USERNAME_ALPHABET = string.ascii_lowercase + string.digits
PASSWORD_SYMBOLS = "!@#$%_-"


class PortalIdentityError(RuntimeError):
    """Raised when the local portal identity state cannot be used."""


def resolve_identity_state_path(path: str = "", *, base_dir: str | Path | None = None) -> Path:
    raw = (path or os.getenv("PORTAL_IDENTITY_STATE") or "output/portal_identity_state.json").strip()
    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = Path(base_dir or os.getcwd()).resolve() / p
    return p


@contextmanager
def _locked_state(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    with open(lock_path, "a+", encoding="utf-8") as lock_f:
        if fcntl is not None:
            fcntl.flock(lock_f.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(lock_f.fileno(), fcntl.LOCK_UN)


def _load_state(path: Path, namespace: str) -> dict:
    if path.exists():
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            raise PortalIdentityError(f"portal identity state 解析失败: {path}: {e}") from e
        if not isinstance(state, dict):
            raise PortalIdentityError(f"portal identity state 顶层不是对象: {path}")
    else:
        state = {}

    secret = str(state.get("secret") or "").strip()
    if not secret:
        secret = base64.b64encode(secrets.token_bytes(32)).decode("ascii")
        state["secret"] = secret
    try:
        base64.b64decode(secret.encode("ascii"), validate=True)
    except Exception as e:
        raise PortalIdentityError(f"portal identity state secret 非 base64: {path}") from e

    if "last_seq" not in state:
        state["last_seq"] = 0
    try:
        state["last_seq"] = int(state["last_seq"])
    except Exception as e:
        raise PortalIdentityError(f"portal identity state last_seq 非整数: {path}") from e
    state.setdefault("namespace", namespace)
    return state


def _write_state(path: Path, state: dict) -> None:
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}.{secrets.token_hex(4)}")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _username_suffix_from_digest(digest: bytes, length: int) -> str:
    out: list[str] = []
    counter = 0
    seed = digest
    while len(out) < length:
        block = hashlib.sha256(seed + counter.to_bytes(2, "big")).digest()
        num = int.from_bytes(block, "big")
        while num and len(out) < length:
            out.append(USERNAME_ALPHABET[num % len(USERNAME_ALPHABET)])
            num //= len(USERNAME_ALPHABET)
        counter += 1
    return "".join(out)


def username_from_sequence(secret: bytes, seq: int, *, namespace: str = "portal-live", length: int = 12) -> str:
    """Map a monotonic sequence to a fixed-width, lowercase account name.

    The sequence remains local and auditable, while the public value is a
    secret-keyed HMAC projection. Without the state secret, adjacent sequence
    values do not reveal adjacent usernames.
    """
    if length < 2:
        raise ValueError("username length must be >= 2")
    msg = f"{namespace}:{int(seq)}".encode("utf-8")
    digest = hmac.new(secret, msg, hashlib.sha256).digest()
    prefix = USERNAME_LETTERS[digest[0] % len(USERNAME_LETTERS)]
    return prefix + _username_suffix_from_digest(digest[1:], length - 1)


def next_username(
    state_path: str | Path = "",
    *,
    namespace: str = "portal-live",
    length: int = 12,
    base_dir: str | Path | None = None,
) -> tuple[str, int]:
    path = resolve_identity_state_path(str(state_path or ""), base_dir=base_dir)
    with _locked_state(path):
        state = _load_state(path, namespace)
        state["last_seq"] = int(state.get("last_seq") or 0) + 1
        secret = base64.b64decode(str(state["secret"]).encode("ascii"), validate=True)
        username = username_from_sequence(secret, int(state["last_seq"]), namespace=namespace, length=length)
        state["namespace"] = namespace
        _write_state(path, state)
        return username, int(state["last_seq"])


def generate_password(length: int = 12, *, symbols: str = PASSWORD_SYMBOLS) -> str:
    if length < 4:
        raise ValueError("password length must be >= 4")
    if not symbols:
        raise ValueError("password symbols must not be empty")

    rng = secrets.SystemRandom()
    required = [
        rng.choice(string.ascii_uppercase),
        rng.choice(string.ascii_lowercase),
        rng.choice(string.digits),
        rng.choice(symbols),
    ]
    alphabet = string.ascii_letters + string.digits + symbols
    required.extend(rng.choice(alphabet) for _ in range(length - len(required)))
    rng.shuffle(required)
    return "".join(required)
