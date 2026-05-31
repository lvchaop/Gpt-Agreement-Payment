"""单 active-run 的 pipeline 进程控制器。

封装 `xvfb-run -a python pipeline.py [args]` 子进程：spawn / 流式收 stdout
到环形日志缓冲 / SIGTERM-优先 stop / 暴露 status + log 给路由层。

GoPay 模式下额外支持 OTP 中转：默认通过 WebUI 内部 HTTP endpoint
把 WhatsApp / 手动补录 OTP 写入 SQLite，gopay.py 轮询该 endpoint。
保留 `GOPAY_OTP_REQUEST path=<file>` 旧格式识别，只作为显式 legacy
file provider 的兼容 fallback。
"""
import json
import os
import re
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional

from . import link_state, settings as s
from . import wa_relay


_lock = threading.Lock()
_proc: Optional[subprocess.Popen] = None
_started_at: Optional[float] = None
_ended_at: Optional[float] = None
_exit_code: Optional[int] = None
_cmd: Optional[list[str]] = None
_mode: Optional[str] = None
_log_lines: list[dict] = []  # {seq, ts, line}
_seq_counter = 0
_otp_file: Optional[Path] = None       # legacy file provider path, if used
_otp_to_db: bool = False               # True when gopay.py waits on WebUI SQLite OTP endpoint
_otp_pending: bool = False             # set when gopay.py asks/waits for OTP
_otp_file_is_temp: bool = False
_active_gopay_phone: str = ""          # digits-only phone for the running gopay flow
_preserve_log_on_next_start: bool = False  # auto-loop sets True so log scrolls across iterations


def _state_path() -> Path:
    return s.get_data_dir() / "webui_runner_state.json"


def _read_state() -> dict:
    try:
        return json.loads(_state_path().read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_state(proc: subprocess.Popen, cmd: list[str], mode: str) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        pgid = os.getpgid(proc.pid)
    except Exception:
        pgid = proc.pid
    payload = {
        "pid": proc.pid,
        "pgid": pgid,
        "cmd": cmd,
        "mode": mode,
        "started_at": time.time(),
    }
    try:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _clear_state(expected_pid: Optional[int] = None) -> None:
    state = _read_state()
    if expected_pid is not None:
        try:
            if int(state.get("pid") or 0) != int(expected_pid):
                return
        except Exception:
            return
    try:
        _state_path().unlink(missing_ok=True)
    except Exception:
        pass


def _pid_alive(pid: int) -> bool:
    try:
        if int(pid) <= 0:
            return False
        os.kill(int(pid), 0)
        return True
    except Exception:
        return False


def _safe_pgid(pid: int) -> int:
    try:
        return os.getpgid(int(pid))
    except Exception:
        return int(pid)


def _kill_pgid_or_pid(pid: int, pgid: Optional[int] = None, *, sig: int = signal.SIGTERM) -> None:
    pid = int(pid)
    pgid = int(pgid or _safe_pgid(pid))
    try:
        os.killpg(pgid, sig)
    except Exception:
        try:
            os.kill(pid, sig)
        except Exception:
            pass


def _wait_pid_gone(pid: int, timeout_s: float) -> bool:
    deadline = time.time() + max(0.0, timeout_s)
    while time.time() < deadline:
        if not _pid_alive(pid):
            return True
        time.sleep(0.1)
    return not _pid_alive(pid)


def _terminate_process_group(pid: int, pgid: Optional[int] = None, *, wait_proc: Optional[subprocess.Popen] = None) -> None:
    pid = int(pid)
    pgid = int(pgid or _safe_pgid(pid))
    _kill_pgid_or_pid(pid, pgid, sig=signal.SIGTERM)
    try:
        if wait_proc is not None:
            wait_proc.wait(timeout=5)
            return
    except subprocess.TimeoutExpired:
        pass
    if not _wait_pid_gone(pid, 5):
        _kill_pgid_or_pid(pid, pgid, sig=signal.SIGKILL)
        if wait_proc is not None:
            try:
                wait_proc.wait(timeout=2)
            except Exception:
                pass
        else:
            _wait_pid_gone(pid, 2)


def _pid_command(pid: int) -> str:
    try:
        return subprocess.check_output(["ps", "-p", str(int(pid)), "-o", "command="], text=True).strip()
    except Exception:
        return ""


def _is_managed_run_command(cmd: str) -> bool:
    root = str(s.ROOT)
    if "pipeline.py" in cmd and root in cmd and "--config" in cmd:
        return True
    if "CTF-pay/card.py" in cmd and root in cmd and "--json-result" in cmd:
        return True
    if "CTF-pay/scripts/paypal_node_rpa.js" in cmd and root in cmd:
        return True
    if "/Google Chrome" in cmd and "paypal_node_rpa_" in cmd and "--user-data-dir=" in cmd:
        return True
    return False


def _managed_orphan_rows() -> list[tuple[int, int, str]]:
    """Find project-owned runner descendants that may outlive WebUI state.

    This is intentionally narrow: only this repo's pipeline/card/node commands
    and Chrome instances with Playwright's paypal_node_rpa temp profile match.
    """
    try:
        out = subprocess.check_output(["ps", "-axo", "pid=,ppid=,command="], text=True)
    except Exception:
        return []
    rows: list[tuple[int, int, str]] = []
    self_pid = os.getpid()
    for line in out.splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) < 3:
            continue
        try:
            pid = int(parts[0])
            ppid = int(parts[1])
        except Exception:
            continue
        if pid == self_pid:
            continue
        cmd = parts[2]
        if _is_managed_run_command(cmd):
            rows.append((pid, ppid, cmd))
    return rows


def _cleanup_persisted_and_orphan_runs(*, include_scan: bool = True) -> int:
    """Best-effort cleanup for runs whose Popen object is no longer in memory."""
    killed = 0
    state = _read_state()
    try:
        pid = int(state.get("pid") or 0)
        pgid = int(state.get("pgid") or 0) or None
    except Exception:
        pid = 0
        pgid = None
    if pid:
        if _pid_alive(pid):
            if _is_managed_run_command(_pid_command(pid)):
                _terminate_process_group(pid, pgid)
                killed += 1
            else:
                _clear_state(pid)
        else:
            _clear_state(pid)

    if include_scan:
        rows = _managed_orphan_rows()
        # Kill parent-ish processes first; Chrome children are handled by pgid
        # but remain as an explicit fallback when a child escaped the group.
        rows.sort(key=lambda item: (0 if "pipeline.py" in item[2] else 1 if "card.py" in item[2] else 2))
        seen_groups: set[int] = set()
        for pid, ppid, _cmd in rows:
            if ppid != 1:
                continue
            if not _pid_alive(pid):
                continue
            pgid = _safe_pgid(pid)
            if pgid in seen_groups:
                continue
            seen_groups.add(pgid)
            _terminate_process_group(pid, pgid)
            killed += 1
    return killed


_PHONE_CONFIG_KEYS = {
    "enabled", "provider", "base_url", "api_key_env", "country", "countries", "service",
    "maxPrice", "max_price", "country_max_prices", "lease_ttl_s", "max_number_attempts", "request_timeout_s", "allocate_path", "otp_path",
    "otp_method", "otp_timeout_s", "otp_poll_interval_s",
    "cancel_retry_attempts", "cancel_retry_interval_s", "stale_cancel_after_s", "watchdog_enabled", "release_path",
    "fail_path", "verified_path", "headers", "allocate_payload",
}


def _read_pay_config() -> dict:
    try:
        return json.loads(s.PAY_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _read_reg_config() -> dict:
    try:
        return json.loads(s.REG_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _runtime_phone_config(phone: Optional[dict], *, method: str = "phone_browser") -> tuple[str, dict]:
    """Create a temporary reg config for Run-page phone overrides.

    The API key is passed via environment instead of being written to disk.
    """
    phone = phone or {}
    reg_cfg = _read_reg_config()
    if not isinstance(reg_cfg, dict):
        reg_cfg = {}
    current = reg_cfg.get("phone") if isinstance(reg_cfg.get("phone"), dict) else {}
    merged = dict(current)
    for key, value in phone.items():
        if key == "api_key":
            continue
        if key in _PHONE_CONFIG_KEYS and value not in (None, ""):
            merged[key] = value
    merged["enabled"] = True
    merged.setdefault("provider", "hero_sms")
    merged.setdefault("base_url", "https://hero-sms.com/stubs/handler_api.php")
    merged.setdefault("api_key_env", "HERO_SMS_API_KEY")
    merged.setdefault("country", "2")
    merged.setdefault("service", "tg")
    reg_cfg["phone"] = merged
    reg_cfg["registration"] = {"method": method if method in {"phone_browser", "phone_protocol"} else "phone_browser"}

    env_overrides: dict = {}
    api_key = str(phone.get("api_key") or "").strip()
    if api_key:
        key_env = str(merged.get("api_key_env") or "HERO_SMS_API_KEY").strip() or "HERO_SMS_API_KEY"
        merged["api_key_env"] = key_env
        env_overrides[key_env] = api_key

    out_dir = s.get_data_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "runtime-reg-phone.json"
    path.write_text(json.dumps(reg_cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path), env_overrides


_LINK_OK_RE = re.compile(r"\[gopay\]\s+midtrans linking ok\s+reference=(\S+)")
_CHARGE_SETTLED_RE = re.compile(r"\[gopay\]\s+charge settled")
# 406「account already linked」signal —— Midtrans 服务端确认该号已绑，
# 不论后续重试是否成功，本地都应该 mark linked 来跟服务端对齐
_LINK_406_RE = re.compile(r"\[gopay\]\s+midtrans linking 406")


def _gopay_auto_otp_enabled() -> bool:
    """Return True when config has a non-manual gopay.otp provider.

    Legacy helper kept for old tests/tools. Current WebUI injects
    WEBUI_GOPAY_OTP_URL and uses the SQLite-backed HTTP provider by default.
    """
    try:
        cfg = json.loads(s.PAY_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return False
    gp = cfg.get("gopay") or {}
    if not isinstance(gp, dict):
        return False
    otp = gp.get("otp") or gp.get("otp_provider") or {}
    if not isinstance(otp, dict):
        return False
    source = str(otp.get("source") or otp.get("type") or "auto").strip().lower()
    if source in ("", "manual", "cli", "stdin"):
        return False
    has_url = bool((otp.get("url") or otp.get("relay_url") or "").strip())
    has_path = bool((otp.get("path") or otp.get("state_file") or otp.get("log_file") or "").strip())
    has_command = bool(otp.get("command") or otp.get("cmd"))
    if source in ("http", "https", "relay", "whatsapp_http", "wa_http"):
        return has_url
    if source in ("file", "state_file", "log", "whatsapp_file", "wa_file"):
        return has_path
    if source in ("command", "cmd"):
        return has_command
    if source == "auto":
        return has_url or has_path or has_command
    return False


def build_cmd(mode: str, paypal: bool, batch: int, workers: int, self_dealer: int,
              register_only: bool, pay_only: bool, gopay: bool = False,
              gopay_otp_file: str = "", count: int = 0,
              target_emails: Optional[list] = None, rt_only: bool = False,
              register_mode: str = "browser", cardw_config_path: str = "") -> list[str]:
    """根据参数拼出最终命令行。"""
    cmd = ["xvfb-run", "-a", "python", "-u", "pipeline.py",
           "--config", str(s.PAY_CONFIG_PATH)]
    if cardw_config_path:
        cmd.extend(["--cardw-config", str(cardw_config_path)])

    def _append_proxy_args() -> None:
        cfg = _read_pay_config()
        trojan = cfg.get("trojan_pool") or {}
        if not trojan.get("enabled"):
            return
        cmd.extend(["--proxy-mode", "trojan-pool"])
        pool_file = str(trojan.get("pool_file") or "output/trojan_pool.txt")
        cmd.extend(["--trojan-pool-file", pool_file])
        cmd.extend(["--trojan-http-start-port", str(int(trojan.get("http_start_port") or 18081))])
        bridge_bin = str(trojan.get("bridge_bin") or "sing-box")
        if bridge_bin:
            cmd.extend(["--trojan-bridge-bin", bridge_bin])
        region_map = {
            "--proxy-region-all": trojan.get("region_all"),
            "--proxy-region-register": trojan.get("region_register"),
            "--proxy-region-checkout": trojan.get("region_checkout"),
            "--proxy-region-payment": trojan.get("region_payment"),
        }
        for flag, value in region_map.items():
            value = str(value or "").strip()
            if value:
                cmd.extend([flag, value])

    _append_proxy_args()
    rm = (register_mode or "browser").strip().lower().replace("-", "_")
    # free_only 两个子模式不需要 paypal / gopay 支付段
    if mode in ("free_register", "free_backfill_rt"):
        if mode == "free_register":
            cmd.append("--free-register")
            if count > 0:
                cmd.extend(["--count", str(count)])
            if rm in ("protocol", "phone_browser", "phone_protocol", "portal_protocol"):
                cmd.extend(["--register-method", rm])
        else:
            cmd.append("--free-backfill-rt")
        return cmd
    if gopay:
        cmd.append("--gopay")
        if gopay_otp_file:
            cmd.extend(["--gopay-otp-file", gopay_otp_file])
    elif paypal:
        cmd.append("--paypal")
    if rm in ("protocol", "phone_browser", "phone_protocol", "portal_protocol"):
        cmd.extend(["--register-method", rm])
    # mode 决定循环结构（daemon ∞ / self_dealer / batch N / 单次）
    if mode == "daemon":
        cmd.append("--daemon")
    elif mode == "self_dealer":
        cmd.extend(["--self-dealer", str(self_dealer)])
    elif mode == "batch":
        cmd.extend(["--batch", str(batch), "--workers", str(workers)])
    # mode == "single" → no extra flags
    # register_only / pay_only 是 modifier，跟 mode 正交（batch + register-only
    # = 批量注册 N 个；single + register-only = 单次注册）
    if register_only:
        cmd.append("--register-only")
    elif pay_only:
        cmd.append("--pay-only")
    if rt_only:
        cmd.append("--rt-only")
    if target_emails:
        joined = ",".join(e.strip() for e in target_emails if e and e.strip())
        if joined:
            cmd.extend(["--target-emails", joined])
    return cmd


def status() -> dict:
    global _proc
    is_running = _proc is not None and _proc.poll() is None
    orphan_state: dict = {}
    orphan_running = False
    if not is_running:
        state = _read_state()
        try:
            state_pid = int(state.get("pid") or 0)
        except Exception:
            state_pid = 0
        if state_pid and _pid_alive(state_pid):
            orphan_state = state
            orphan_running = True
            is_running = True
        elif state_pid:
            _clear_state(state_pid)
    return {
        "running": is_running,
        "started_at": orphan_state.get("started_at") if orphan_running else _started_at,
        "ended_at": _ended_at,
        "exit_code": _exit_code if not is_running else None,
        "cmd": orphan_state.get("cmd") if orphan_running else _cmd,
        "mode": orphan_state.get("mode") if orphan_running else _mode,
        "pid": orphan_state.get("pid") if orphan_running else (_proc.pid if is_running and _proc else None),
        "orphan": orphan_running,
        "log_count": _seq_counter,
        "otp_pending": _otp_pending,
    }


def start(*, mode: str, paypal: bool = True, batch: int = 0, workers: int = 3,
          self_dealer: int = 0, register_only: bool = False, pay_only: bool = False,
          gopay: bool = False, count: int = 0, register_mode: str = "browser",
          env_overrides: Optional[dict] = None,
          target_emails: Optional[list] = None, rt_only: bool = False,
          phone: Optional[dict] = None) -> dict:
    global _proc, _started_at, _ended_at, _exit_code, _cmd, _mode
    global _log_lines, _seq_counter, _otp_file, _otp_to_db, _otp_pending, _otp_file_is_temp
    global _active_gopay_phone
    with _lock:
        if _proc is not None and _proc.poll() is None:
            raise RuntimeError("a pipeline is already running")
        _cleanup_persisted_and_orphan_runs(include_scan=True)

        # OTP 默认走 WebUI SQLite endpoint；不再创建临时 FIFO 文件。
        otp_p: Optional[Path] = None

        rm = (register_mode or "browser").strip().lower()
        cardw_config_path = ""
        runtime_env_overrides = dict(env_overrides or {})
        if rm in ("phone", "phone_browser", "phone_protocol"):
            cardw_config_path, phone_env = _runtime_phone_config(
                phone,
                method="phone_protocol" if rm == "phone_protocol" else "phone_browser",
            )
            runtime_env_overrides.update(phone_env)

        cmd = build_cmd(mode, paypal, batch, workers, self_dealer,
                        register_only, pay_only, gopay=gopay,
                        gopay_otp_file="", count=count,
                        target_emails=target_emails, rt_only=rt_only,
                        register_mode=register_mode,
                        cardw_config_path=cardw_config_path)

        # GoPay link-state pre-flight: if the configured phone is currently
        # linked from a prior successful charge, GoPay will reject the next
        # linking attempt with 406 "account already linked". Refuse to start
        # until an external service POSTs to /api/gopay/link-state/unlink.
        active_phone = ""
        if gopay:
            cfg = _read_pay_config()
            active_phone = link_state.phone_from_gopay_config(cfg)
            if active_phone and link_state.is_linked(active_phone):
                raise RuntimeError(
                    f"gopay phone {active_phone} is currently linked; "
                    "external service must POST /api/gopay/link-state/unlink first"
                )

        # Reset (auto-loop 跨 iteration 时保留之前的日志，方便用户连续看)
        global _preserve_log_on_next_start
        if not _preserve_log_on_next_start:
            _log_lines = []
            _seq_counter = 0
        _preserve_log_on_next_start = False
        _started_at = time.time()
        _ended_at = None
        _exit_code = None
        _cmd = cmd
        _mode = mode
        _otp_file = otp_p
        _otp_to_db = False
        _otp_file_is_temp = otp_p is not None
        _otp_pending = False
        _active_gopay_phone = active_phone

        env = {**os.environ, "PYTHONUNBUFFERED": "1"}
        if gopay:
            env["WEBUI_GOPAY_OTP_URL"] = wa_relay.otp_url()
        # Portal 抓包模式：默认只保留浏览器手机号 trace；协议 auth trace 需要显式开启。
        # 只落盘，不把每个 HTTP 片段刷到 WebUI 日志里。
        env["AUTH_TRACE_DUMP"] = "0"
        env["AUTH_HTTP_TRACE"] = "0"
        env["AUTH_TRACE_INCLUDE_COOKIE"] = "0"
        env.setdefault("PHONE_TRACE_DUMP", "1")
        # 注册路径切换：browser=Camoufox/Playwright；protocol=auth_flow；phone_*=手机号入口/协议；portal_protocol=Live/portal 纯协议
        env["WEBUI_REG_MODE"] = (
            "portal_protocol"
            if rm == "portal_protocol"
            else (
                "phone_protocol"
                if rm == "phone_protocol"
                else ("phone_browser" if rm in ("phone", "phone_browser") else ("protocol" if rm == "protocol" else "browser"))
            )
        )
        if runtime_env_overrides:
            for k, v in runtime_env_overrides.items():
                if v is None:
                    env.pop(str(k), None)
                else:
                    env[str(k)] = str(v)
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(s.ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env,
                # 让 pipeline 子进程独立成 session leader，webui 后端重启时
                # 不会随之被杀。stop() 用 killpg 显式终止整组。
                start_new_session=True,
            )
        except FileNotFoundError as e:
            _ended_at = time.time()
            _exit_code = -1
            raise RuntimeError(f"failed to spawn: {e}") from e
        _proc = proc
        _write_state(proc, cmd, mode)

        threading.Thread(target=_drain, args=(proc,), daemon=True).start()
    return status()


def _detect_otp_wait_target(line: str) -> tuple[str, Optional[Path]]:
    """Return (kind, path) from OTP wait markers."""
    if "PAYPAL_NEW_USER_OTP_REQUEST" in line:
        m = re.search(r"\bpath=(.+?)\s*$", line)
        if m:
            return "file", Path(m.group(1).strip().strip("'\""))
        return "file", _otp_file

    if "GOPAY_OTP_REQUEST" in line:
        m = re.search(r"\bpath=(.+?)\s*$", line)
        if m:
            return "file", Path(m.group(1).strip().strip("'\""))
        return "file", _otp_file

    # Legacy configured file provider path.
    m = re.search(r"\[gopay\]\s+waiting WhatsApp OTP from file:\s*(.+?)\s*$", line)
    if m:
        return "file", Path(m.group(1).strip().strip("'\""))

    # New DB-backed WebUI provider, e.g.
    # [gopay] waiting WhatsApp OTP from relay: http://127.0.0.1:8765/api/whatsapp/latest-otp?...
    if re.search(r"\[gopay\]\s+waiting WhatsApp OTP from relay:", line):
        return "db", None
    return "", None


def _drain(proc: subprocess.Popen) -> None:
    global _ended_at, _exit_code, _seq_counter, _log_lines, _otp_pending, _otp_file, _otp_to_db, _otp_file_is_temp
    last_link_ref = ""
    try:
        if proc.stdout is None:
            return
        for line in iter(proc.stdout.readline, ""):
            line = line.rstrip()
            if not line:
                continue
            with _lock:
                _seq_counter += 1
                _log_lines.append({"seq": _seq_counter, "ts": time.time(), "line": line})
                if len(_log_lines) > 3000:
                    _log_lines = _log_lines[-2000:]
                # Detect GoPay OTP request/wait markers.  The second form is
                # used by the configured WhatsApp relay provider; making it
                # pending lets the existing WebUI OTP modal act as a fallback
                # when WhatsApp hides OTP bodies from linked devices.
                wait_kind, wait_path = _detect_otp_wait_target(line)
                if wait_kind:
                    _otp_to_db = wait_kind == "db"
                    _otp_file = wait_path
                    _otp_file_is_temp = _otp_file_is_temp or "GOPAY_OTP_REQUEST" in line
                    _otp_pending = True

                # Track the merchant reference from the linking step so we can
                # store it alongside the linked-state record on charge settle.
                m = _LINK_OK_RE.search(line)
                if m:
                    last_link_ref = m.group(1).strip().strip(",.")

                # 提前检测 406：Midtrans 已经认定 phone 绑了，本地应同步。
                # 不等 charge settled 才更新——失败的支付也会留下 linked 状态，
                # 否则下一单还会盲目重试，被同样的 406 拦下。
                if _LINK_406_RE.search(line) and _active_gopay_phone:
                    try:
                        link_state.mark_linked(
                            _active_gopay_phone,
                            payment_ref=last_link_ref or "auto_from_406",
                            source="pipeline_406_detect",
                        )
                    except Exception:
                        pass

                # Mark the configured phone as linked when a charge settles.
                # GoPay treats the phone as bound at this point, so subsequent
                # linking attempts return 406 unless an external service has
                # called /api/gopay/link-state/unlink in the meantime.
                if _CHARGE_SETTLED_RE.search(line) and _active_gopay_phone:
                    try:
                        link_state.mark_linked(
                            _active_gopay_phone,
                            payment_ref=last_link_ref,
                            source="pipeline",
                        )
                    except Exception:
                        pass
    finally:
        proc.wait()
        _clear_state(proc.pid)
        with _lock:
            _ended_at = time.time()
            _exit_code = proc.returncode
            _otp_pending = False
            # Cleanup OTP file.  For the auto relay path this intentionally
            # removes stale OTPs too; future waits use mtime checks, but an
            # empty/clean file is easier to reason about.
            if _otp_file is not None:
                try:
                    _otp_file.unlink(missing_ok=True)
                except Exception:
                    pass


def stop() -> dict:
    global _proc
    with _lock:
        proc = _proc
    if proc is not None and proc.poll() is None:
        # subprocess 是独立 session leader（start_new_session=True），用 killpg
        # 终止整组，否则只 SIGTERM 父进程会留下 xvfb-run/python pipeline 孤儿。
        _terminate_process_group(proc.pid, wait_proc=proc)
        _clear_state(proc.pid)
    _cleanup_persisted_and_orphan_runs(include_scan=True)
    return status()


def submit_otp(value: str) -> dict:
    """Front-end calls this with the OTP user typed. Stores it in DB by default."""
    global _otp_pending
    with _lock:
        if not _otp_pending:
            raise RuntimeError("no OTP currently requested")
        path = _otp_file
        use_db = _otp_to_db
    if use_db:
        wa_relay.submit_manual_otp(value)
    else:
        if path is None:
            raise RuntimeError("no OTP file currently requested")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value.strip(), encoding="utf-8")
    with _lock:
        _otp_pending = False
    return status()


def append_log(line: str) -> None:
    """Append a synthetic line into the rolling log (used by auto-loop to inject
    [auto-loop] progress markers between subprocess iterations)."""
    global _seq_counter, _log_lines
    with _lock:
        _seq_counter += 1
        _log_lines.append({"seq": _seq_counter, "ts": time.time(), "line": line})
        if len(_log_lines) > 3000:
            _log_lines = _log_lines[-2000:]


def preserve_log_on_next_start() -> None:
    """Auto-loop calls before each runner.start() to keep the rolling log
    instead of wiping it on every iteration."""
    global _preserve_log_on_next_start
    _preserve_log_on_next_start = True


def get_lines_since(since_seq: int = 0, limit: int = 1000) -> list[dict]:
    with _lock:
        return [e for e in _log_lines if e["seq"] > since_seq][:limit]


def get_tail(n: int = 200) -> list[dict]:
    with _lock:
        return _log_lines[-n:]
