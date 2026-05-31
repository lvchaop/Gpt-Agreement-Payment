"""Mode-aware configuration health checks for pipeline starts.

The goal is to fail fast before a real registration/payment run consumes time
or external state.  The checks are intentionally local and side-effect free:
they inspect SQLite runtime config, exported JSON config, and local inventory,
but they do not call Cloudflare/OpenAI/Stripe/PayPal/GoPay.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from . import settings as s
from .account_inventory import build_accounts_inventory
from .db import get_db
from . import wa_relay


_PLACEHOLDER_MARKERS = (
    "your_",
    "your-",
    "example.com",
    "example street",
    "tester@example.com",
    "you@your-catch-all-zone.com",
    "your_paypal_password",
    "your_6_digit_gopay_pin",
    "subdomain.example.com",
    "change_me",
    "changeme",
    "todo",
)


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _is_missing(value: Any, *, allow_example: bool = False) -> bool:
    text = _text(value)
    if not text:
        return True
    if allow_example:
        return False
    low = text.lower()
    if low in {"", "none", "null", "undefined"}:
        return True
    return any(marker in low for marker in _PLACEHOLDER_MARKERS)


def _get(obj: Any, path: str, default: Any = None) -> Any:
    cur = obj
    for part in path.split("."):
        if not isinstance(cur, dict):
            return default
        cur = cur.get(part)
    return default if cur is None else cur


def _load_json(path: Path) -> tuple[dict, str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}, f"文件不存在: {path}"
    except Exception as e:
        return {}, f"JSON 解析失败: {path}: {e}"
    if not isinstance(data, dict):
        return {}, f"JSON 顶层不是对象: {path}"
    return data, ""


def _resolve_reg_config_path(pay_cfg: dict) -> Path:
    raw = _text(_get(pay_cfg, "fresh_checkout.auth.auto_register.config_path"))
    if not raw:
        return s.REG_CONFIG_PATH
    p = Path(raw)
    return p if p.is_absolute() else (s.ROOT / p)


def _check(
    checks: list[dict],
    name: str,
    status: str,
    message: str,
    *,
    missing: list[str] | None = None,
    blocking: bool | None = None,
    details: str = "",
    action: str = "",
) -> None:
    if blocking is None:
        blocking = status == "fail"
    checks.append({
        "name": name,
        "status": status,
        "message": message,
        "missing": missing or [],
        "blocking": bool(blocking),
        "details": details,
        "action": action,
    })


def _effective_cloudflare_secret_presence() -> dict[str, bool]:
    secrets = get_db().get_runtime_json("secrets", {})
    cf = (secrets.get("cloudflare") or {}) if isinstance(secrets, dict) else {}
    return {
        "cloudflare.api_token": bool(
            _text(os.getenv("CF_API_TOKEN"))
            or _text(cf.get("kv_api_token"))
            or _text(cf.get("api_token"))
        ),
        "cloudflare.account_id": bool(
            _text(os.getenv("CF_ACCOUNT_ID"))
            or _text(cf.get("account_id"))
        ),
        "cloudflare.otp_kv_namespace_id": bool(
            _text(os.getenv("CF_OTP_KV_NAMESPACE_ID"))
            or _text(cf.get("otp_kv_namespace_id"))
        ),
    }


def _missing_paths(obj: dict, paths: list[str]) -> list[str]:
    return [p for p in paths if _is_missing(_get(obj, p))]


def _requires_registration(req: dict) -> bool:
    mode = _text(req.get("mode")) or "single"
    if mode == "free_register":
        return True
    if mode == "free_backfill_rt":
        return False
    return not bool(req.get("pay_only"))


def _requested_register_mode(req: dict) -> str:
    return _text(req.get("register_mode")).lower().replace("-", "_")


def _requires_email_otp(req: dict) -> bool:
    mode = _text(req.get("mode")) or "single"
    if _requested_register_mode(req) == "portal_protocol":
        return False
    # free_backfill_rt does not create a new mailbox, but OAuth login still
    # needs the OpenAI email OTP provider for existing accounts.
    return _requires_registration(req) or mode == "free_backfill_rt" or bool(req.get("register_only"))


def _payment_kind(req: dict) -> str:
    mode = _text(req.get("mode")) or "single"
    if mode in {"free_register", "free_backfill_rt"} or bool(req.get("register_only")):
        return "none"
    if bool(req.get("gopay")):
        return "gopay"
    if bool(req.get("paypal", True)):
        return "paypal"
    return "card"


def _registration_method(req: dict, reg_cfg: dict | None = None) -> str:
    requested = _requested_register_mode(req)
    if requested:
        return requested
    reg = (reg_cfg or {}).get("registration") if isinstance((reg_cfg or {}).get("registration"), dict) else {}
    return _text(reg.get("method")).lower().replace("-", "_") or "browser"


def _config_has_embedded_auth(pay_cfg: dict) -> bool:
    auth = _get(pay_cfg, "fresh_checkout.auth", {})
    if not isinstance(auth, dict):
        return False
    return any(
        not _is_missing(auth.get(key), allow_example=True)
        for key in ("session_token", "access_token", "cookie_header")
    )


def _check_config_files(checks: list[dict], req: dict) -> tuple[dict, dict, Path]:
    pay_cfg, pay_err = _load_json(s.PAY_CONFIG_PATH)
    if pay_err:
        _check(
            checks,
            "pay_config",
            "fail",
            "支付/运行配置文件不可用",
            missing=[str(s.PAY_CONFIG_PATH)],
            details=pay_err,
            action="先在配置向导导出配置，或修复 CTF-pay/config.paypal.json",
        )
        return {}, {}, s.REG_CONFIG_PATH
    _check(
        checks,
        "pay_config",
        "ok",
        "支付/运行配置文件可读取",
        details=str(s.PAY_CONFIG_PATH),
        blocking=False,
    )

    reg_path = _resolve_reg_config_path(pay_cfg)
    reg_cfg: dict = {}
    if _requires_registration(req):
        reg_cfg, reg_err = _load_json(reg_path)
        if reg_err:
            _check(
                checks,
                "reg_config",
                "fail",
                "注册配置文件不可用",
                missing=[str(reg_path)],
                details=reg_err,
                action="重新导出配置向导，确认 fresh_checkout.auth.auto_register.config_path 指向真实 CTF-reg 配置",
            )
        else:
            _check(
                checks,
                "reg_config",
                "ok",
                "注册配置文件可读取",
                details=str(reg_path),
                blocking=False,
            )
    return pay_cfg, reg_cfg, reg_path


def _check_cloudflare_kv(checks: list[dict], req: dict, reg_cfg: dict | None = None) -> None:
    if _registration_method(req, reg_cfg) == "portal_protocol":
        _check(
            checks,
            "cloudflare_kv_secrets",
            "ok",
            "portal_protocol 不需要 Cloudflare KV 邮箱 OTP",
            blocking=False,
        )
        return
    mail = (reg_cfg or {}).get("mail") if isinstance((reg_cfg or {}).get("mail"), dict) else {}
    if _text(mail.get("mode")) == "imap_list":
        _check(
            checks,
            "email_otp_provider",
            "ok",
            "邮箱 OTP 使用 IMAP 邮箱列表",
            blocking=False,
        )
        return
    presence = _effective_cloudflare_secret_presence()
    missing = [name for name, ok in presence.items() if not ok]
    if not missing:
        _check(
            checks,
            "cloudflare_kv_secrets",
            "ok",
            "Cloudflare KV OTP 凭证已配置",
            details="来源：环境变量或 SQLite runtime_meta[secrets].cloudflare",
            blocking=False,
        )
        return

    if _requires_email_otp(req):
        _check(
            checks,
            "cloudflare_kv_secrets",
            "fail",
            "注册 / OAuth 邮箱 OTP 需要 Cloudflare KV 凭证",
            missing=missing,
            action="去配置向导的 Cloudflare KV 步骤重新保存，或写入 SQLite runtime_meta[secrets].cloudflare",
        )
    else:
        _check(
            checks,
            "cloudflare_kv_secrets",
            "warn",
            "Cloudflare KV OTP 凭证缺失；pay-only 支付可继续，但后续补 RT/CPA 可能失败",
            missing=missing,
            blocking=False,
            action="如果需要自动拿 refresh_token，请先补齐 Cloudflare KV 凭证",
        )


def _check_registration_config(checks: list[dict], req: dict, reg_cfg: dict) -> None:
    if not _requires_registration(req):
        return
    method = _registration_method(req, reg_cfg)
    if method == "portal_protocol":
        portal = reg_cfg.get("portal_protocol") if isinstance(reg_cfg.get("portal_protocol"), dict) else {}
        state_path = _text(portal.get("state_path") or "output/portal_identity_state.json")
        if _payment_kind(req) != "none":
            _check(
                checks,
                "portal_protocol_scope",
                "fail",
                "portal_protocol 当前只产出 Live/portal 账号密码，不产出 ChatGPT session",
                action="Run 页勾选 --register-only 后再启动；支付链路继续使用 browser/protocol/phone_* 注册方式",
            )
        else:
            _check(
                checks,
                "portal_protocol",
                "ok",
                "portal_protocol 账号生成配置可用",
                details=f"state_path={state_path}",
                blocking=False,
            )
        return
    if method in {"phone_browser", "phone_protocol"}:
        phone = reg_cfg.get("phone") if isinstance(reg_cfg.get("phone"), dict) else {}
        phone_override = req.get("phone") if isinstance(req.get("phone"), dict) else {}
        if phone_override:
            phone = {
                **phone,
                **{k: v for k, v in phone_override.items() if v not in (None, "")},
            }
        provider = _text(phone.get("provider")).lower().replace("-", "_") or "http"
        is_hero_sms = provider in {"hero", "hero_sms", "smshub", "sms_hub", "sms_activate", "smsactivate"}
        countries = phone.get("countries") if isinstance(phone.get("countries"), list) else []
        has_country = bool(_text(phone.get("country")) or countries)
        required = ("base_url", "service") if is_hero_sms else ("base_url", "allocate_path", "otp_path")
        missing_phone = [key for key in required if _is_missing(phone.get(key))]
        if is_hero_sms and not has_country:
            missing_phone.append("country/countries")
        runtime_enabled = _text(req.get("register_mode")).lower().replace("-", "_") in {"phone_browser", "phone_protocol"}
        if not phone.get("enabled") and not runtime_enabled:
            missing_phone.insert(0, "enabled")
        if is_hero_sms and _text(phone.get("country")) and not _text(phone.get("country")).isdigit():
            missing_phone.append("country")
        if is_hero_sms:
            bad_countries = [str(c) for c in countries if str(c).strip() and not str(c).strip().isdigit()]
            if bad_countries:
                missing_phone.append("countries")
        auth_hint = _text(phone.get("api_key")) or _text(os.getenv(_text(phone.get("api_key_env")) or "PHONE_PROVIDER_API_KEY"))
        if is_hero_sms and not auth_hint:
            missing_phone.append("api_key/api_key_env")
        if missing_phone:
            _check(
                checks,
                "phone_provider",
                "fail",
                "Hero SMS 手机号注册配置不完整" if is_hero_sms else "手机号注册需要 phone provider 配置",
                missing=[f"phone.{x}" for x in missing_phone],
                action=(
                    "在 Web 配置向导步骤 03 选择手机号，填写 Hero API Key；或配置 provider=hero_sms、base_url=https://hero-sms.com/stubs/handler_api.php、service=tg、country=2，并设置 HERO_SMS_API_KEY；拿号/取码使用 getNumberV2/getStatusV2"
                    if is_hero_sms
                    else "在注册配置里启用 phone，并配置拿号接口 allocate_path 与验证码接口 otp_path"
                ),
            )
        else:
            _check(
                checks,
                "phone_provider",
                "ok" if auth_hint or is_hero_sms else "warn",
                "Hero SMS provider 已配置" if is_hero_sms else ("手机号 provider 已配置" if auth_hint else "手机号 provider 已配置；未检测到 API key（若接口无需鉴权可忽略）"),
                blocking=False,
                details=(
                    f"{_text(phone.get('base_url'))} service={_text(phone.get('service'))} country={_text(phone.get('country')) or ','.join(str(c) for c in countries)} maxPrice={_text(phone.get('maxPrice') or phone.get('max_price')) or '<empty>'}"
                    if is_hero_sms
                    else _text(phone.get("base_url"))
                ),
            )
    mail = reg_cfg.get("mail") if isinstance(reg_cfg.get("mail"), dict) else {}
    if _text(mail.get("mode")) == "imap_list":
        try:
            count = len(get_db().iter_mail_accounts())
        except Exception:
            count = 0
        if count > 0:
            _check(
                checks,
                "mail_accounts",
                "ok",
                "IMAP 邮箱账号库已配置",
                details=f"sqlite:mail_accounts count={count}",
                blocking=False,
            )
        else:
            _check(
                checks,
                "mail_accounts",
                "fail",
                "IMAP 邮箱账号库为空",
                missing=["mail_accounts"],
                details="sqlite:mail_accounts count=0",
                action="在配置向导邮箱步骤保存账号列表",
            )
        return
    domains = mail.get("catch_all_domains")
    has_domain = False
    if isinstance(domains, list):
        has_domain = any(not _is_missing(x) for x in domains)
    has_domain = has_domain or not _is_missing(mail.get("catch_all_domain"))
    if not has_domain:
        _check(
            checks,
            "mail_domains",
            "fail",
            "注册需要 catch-all 邮箱域名",
            missing=["mail.catch_all_domain 或 mail.catch_all_domains"],
            action="在配置向导 Cloudflare 步骤填写 zone_names 后重新导出配置",
        )
    else:
        _check(
            checks,
            "mail_domains",
            "ok",
            "注册邮箱域名已配置",
            blocking=False,
        )

    captcha_key = _text(_get(reg_cfg, "captcha.client_key"))
    if not captcha_key:
        _check(
            checks,
            "captcha",
            "warn",
            "注册 captcha client_key 未配置；遇到验证码时可能失败",
            missing=["captcha.client_key"],
            blocking=False,
            action="如近期注册触发验证码，先在配置向导补打码平台配置",
        )


def _check_payment_config(checks: list[dict], req: dict, pay_cfg: dict) -> None:
    kind = _payment_kind(req)
    if kind == "none":
        _check(checks, "payment_config", "ok", "当前模式不走支付", blocking=False)
        return

    if kind == "gopay":
        gp = pay_cfg.get("gopay") if isinstance(pay_cfg.get("gopay"), dict) else {}
        missing = [
            key for key in ("country_code", "phone_number", "pin")
            if _is_missing(gp.get(key))
        ]
        if missing:
            _check(
                checks,
                "gopay_config",
                "fail",
                "GoPay 支付配置不完整",
                missing=[f"gopay.{x}" for x in missing],
                action="在配置向导 GoPay 步骤填写国家码、手机号和 6 位 PIN 后重新导出",
            )
        else:
            _check(checks, "gopay_config", "ok", "GoPay 支付配置已配置", blocking=False)

        wa = wa_relay.status()
        if wa.get("status") == "connected":
            _check(
                checks,
                "whatsapp_relay",
                "ok",
                "WhatsApp relay 已连接，可自动接收 GoPay OTP",
                details=f"engine={wa.get('engine')}",
                blocking=False,
            )
        else:
            _check(
                checks,
                "whatsapp_relay",
                "warn",
                "WhatsApp relay 当前未连接；GoPay OTP 将等待自动 relay 或前端手动补录",
                details=f"status={wa.get('status')}",
                blocking=False,
                action="如需自动接收 GoPay OTP，先打开 WhatsApp 登录入口扫码连接",
            )
        return

    if kind == "paypal":
        pp = pay_cfg.get("paypal") if isinstance(pay_cfg.get("paypal"), dict) else {}
        flow = _text(pp.get("flow") or "existing_account").lower().replace("-", "_")
        if flow in {"new_user", "sandbox_new_user", "guest", "guest_checkout"}:
            def _load_json_rows(path_value: str, label: str) -> tuple[list[dict], Path]:
                path = Path(path_value)
                if not path.is_absolute():
                    path = s.ROOT / path
                raw = path.read_text(encoding="utf-8").strip()
                rows = json.loads(raw) if raw.startswith("[") else [
                    json.loads(line)
                    for line in raw.splitlines()
                    if line.strip() and not line.strip().startswith("#")
                ]
                if not isinstance(rows, list) or not rows:
                    raise ValueError(f"{label} is empty")
                if not all(isinstance(row, dict) for row in rows):
                    raise ValueError(f"{label} rows must be objects")
                return rows, path

            phones_file = _text(
                pp.get("phones_file")
                or pp.get("new_user_phones_file")
                or pp.get("phone_pool_file")
                or "output/paypal_test_phones.jsonl"
            )
            try:
                phone_rows, phone_path = _load_json_rows(phones_file, "phone pool")
                raw_phone_index = pp.get("phone_index")
                if raw_phone_index in (None, "", "round_robin"):
                    raw_phone_index = 0
                phone_index = int(raw_phone_index)
                if phone_index < 0 or phone_index >= len(phone_rows):
                    raise IndexError(f"phone_index={phone_index}, rows={len(phone_rows)}")
                selected_phone = phone_rows[phone_index]
                if _is_missing(
                    selected_phone.get("phone") or selected_phone.get("phone_number") or selected_phone.get("number"),
                    allow_example=True,
                ):
                    raise ValueError("selected phone missing phone/phone_number/number")
            except Exception as e:
                _check(
                    checks,
                    "paypal_phone_pool",
                    "fail",
                    "PayPal 新用户手机号池不可用",
                    details=str(e),
                    action="检查 paypal.phones_file；新用户身份已运行时生成，不需要账号池",
                )
                return

            def _card_ready(card: dict) -> bool:
                if not isinstance(card, dict):
                    return False
                has_number = not _is_missing(card.get("number") or card.get("card_number"), allow_example=True)
                has_cvc = not _is_missing(card.get("cvc") or card.get("cvv"), allow_example=True)
                has_expiry = not _is_missing(card.get("expiry") or card.get("exp"), allow_example=True)
                has_exp_parts = (
                    not _is_missing(card.get("exp_month") or card.get("month"), allow_example=True)
                    and not _is_missing(card.get("exp_year") or card.get("year"), allow_example=True)
                )
                return has_number and has_cvc and (has_expiry or has_exp_parts)

            cards_file = _text(pp.get("cards_file") or pp.get("new_user_cards_file") or pp.get("card_pool_file"))
            selected_card = None
            if cards_file:
                try:
                    card_rows, card_path = _load_json_rows(cards_file, "card pool")
                    raw_card_index = pp.get("card_index")
                    if raw_card_index in (None, "", "round_robin", "random"):
                        raw_card_index = 0
                    card_index = int(raw_card_index)
                    if card_index < 0 or card_index >= len(card_rows):
                        raise IndexError(f"card_index={card_index}, rows={len(card_rows)}")
                    selected_card = card_rows[card_index]
                    if pp.get("card_index") == "random":
                        selected_card = next((c for c in card_rows if _card_ready(c)), selected_card)
                    if not _card_ready(selected_card):
                        raise ValueError("selected card missing number/cvc/expiry")
                except Exception as e:
                    _check(
                        checks,
                        "paypal_card_pool",
                        "fail",
                        "PayPal 新用户测试卡池不可用",
                        details=str(e),
                        action="检查 paypal.cards_file，或删除该字段改用 Step 07/cards",
                    )
                    return
            else:
                cards = pay_cfg.get("cards") if isinstance(pay_cfg.get("cards"), list) else []
                selected_card = next((c for c in cards if _card_ready(c)), None)
                if selected_card is None:
                    _check(
                        checks,
                        "paypal_card_pool",
                        "fail",
                        "PayPal 新用户缺少可用测试卡",
                        missing=["paypal.cards_file 或 cards[0]"],
                        action="在 Step 07/cards 配测试卡，或配置 paypal.cards_file 单独卡池",
                    )
                    return

            _check(
                checks,
                "paypal_config",
                "ok",
                "PayPal 新用户运行时身份、手机号池与测试卡已配置",
                details=f"email=random gmail; address=meiguodizhi; phones={phone_path}; card={'paypal.cards_file' if cards_file else 'cards'}",
                blocking=False,
            )
        else:
            missing = [
                key for key in ("email", "password")
                if _is_missing(pp.get(key))
            ]
            if missing:
                _check(
                    checks,
                    "paypal_config",
                    "fail",
                    "PayPal 支付配置不完整",
                    missing=[f"paypal.{x}" for x in missing],
                    action="在配置向导 PayPal 步骤填写邮箱和密码后重新导出，或将 flow 改为 new_user 并配置手机号池",
                )
            else:
                _check(checks, "paypal_config", "ok", "PayPal 支付配置已配置", blocking=False)
        return

    cards = pay_cfg.get("cards") if isinstance(pay_cfg.get("cards"), list) else []
    usable = [
        c for c in cards
        if isinstance(c, dict)
        and all(not _is_missing(c.get(k), allow_example=True) for k in ("number", "cvc", "exp_month", "exp_year"))
    ]
    if not usable:
        _check(
            checks,
            "card_config",
            "fail",
            "卡支付配置不完整",
            missing=["cards[0].number", "cards[0].cvc", "cards[0].exp_month", "cards[0].exp_year"],
            action="在配置向导卡信息步骤填写卡信息后重新导出",
        )
    else:
        first = str(usable[0].get("number") or "")
        if first.startswith("424242"):
            _check(
                checks,
                "card_config",
                "warn",
                "检测到疑似 Stripe 测试卡号；真实支付前请确认已换成真实卡",
                blocking=False,
            )
        else:
            _check(checks, "card_config", "ok", "卡支付配置已配置", blocking=False)


def _check_pay_only_inventory(checks: list[dict], req: dict, pay_cfg: dict) -> None:
    if not bool(req.get("pay_only")):
        return
    inv = build_accounts_inventory()
    eligible = int((inv.get("counts") or {}).get("pay_only_eligible", 0) or 0)
    if eligible > 0:
        _check(
            checks,
            "pay_only_inventory",
            "ok",
            f"可复用账号库存 {eligible} 个",
            blocking=False,
        )
        return
    if _config_has_embedded_auth(pay_cfg):
        _check(
            checks,
            "pay_only_inventory",
            "warn",
            "数据库暂无可复用账号，将回退使用 config 里的 auth",
            blocking=False,
        )
        return
    _check(
        checks,
        "pay_only_inventory",
        "fail",
        "pay-only 没有可复用账号，且 config 里没有可回退 auth",
        missing=["registered_accounts 可复用账号", "fresh_checkout.auth.session_token/access_token/cookie_header"],
        action="先跑 register-only/注册流程生成账号，或在配置里填入可用 session/access token",
    )


def _check_cpa(checks: list[dict], req: dict, pay_cfg: dict) -> None:
    cpa = pay_cfg.get("cpa") if isinstance(pay_cfg.get("cpa"), dict) else {}
    mode = _text(req.get("mode")) or "single"
    if not cpa.get("enabled"):
        if mode in {"free_register", "free_backfill_rt"}:
            _check(
                checks,
                "cpa_config",
                "warn",
                "CPA 未启用；free 模式会注册/补 RT，但不会推 CPA",
                blocking=False,
            )
        return

    required = ["base_url", "admin_key"]
    missing = [f"cpa.{p}" for p in required if _is_missing(cpa.get(p), allow_example=True)]

    if missing:
        _check(
            checks,
            "cpa_config",
            "fail" if mode in {"free_register", "free_backfill_rt"} else "warn",
            "CPA 配置不完整",
            missing=missing,
            blocking=mode in {"free_register", "free_backfill_rt"},
            action="在配置向导 CPA 步骤填写 base_url/admin_key 后重新导出",
        )
    else:
        _check(checks, "cpa_config", "ok", "CPA 配置已配置", blocking=False)


def _check_team_system(checks: list[dict], req: dict, pay_cfg: dict) -> None:
    mode = _text(req.get("mode")) or "single"
    if mode != "daemon":
        return
    ts = pay_cfg.get("team_system") if isinstance(pay_cfg.get("team_system"), dict) else {}
    missing = []
    if not ts.get("enabled"):
        missing.append("team_system.enabled")
    for key in ("base_url", "username", "password"):
        if _is_missing(ts.get(key), allow_example=True):
            missing.append(f"team_system.{key}")
    if missing:
        _check(
            checks,
            "team_system",
            "fail",
            "daemon 需要 team_system 配置",
            missing=missing,
            action="在配置向导 Team System 步骤补齐后重新导出配置",
        )
    else:
        _check(checks, "team_system", "ok", "team_system 配置已配置", blocking=False)


def _check_free_backfill_inventory(checks: list[dict], req: dict) -> None:
    if _text(req.get("mode")) != "free_backfill_rt":
        return
    inv = build_accounts_inventory()
    counts = inv.get("counts") or {}
    total = int(counts.get("registered_total", 0) or 0)
    candidates = int(counts.get("rt_missing", 0) or 0) + int(counts.get("rt_retryable", 0) or 0)
    if total <= 0:
        _check(
            checks,
            "backfill_inventory",
            "fail",
            "数据库里没有可补 RT 的老账号",
            missing=["registered_accounts"],
            action="先跑注册流程生成账号库存",
        )
    elif candidates <= 0:
        _check(
            checks,
            "backfill_inventory",
            "warn",
            "账号库存存在，但当前没有 RT 待补/可重试账号",
            blocking=False,
        )
    else:
        _check(checks, "backfill_inventory", "ok", f"RT 待补/可重试账号 {candidates} 个", blocking=False)


def build_config_health(req: dict | None = None) -> dict:
    req = dict(req or {})
    req.setdefault("mode", "single")
    req.setdefault("paypal", True)
    checks: list[dict] = []

    pay_cfg, reg_cfg, reg_path = _check_config_files(checks, req)
    if pay_cfg:
        _check_cloudflare_kv(checks, req, reg_cfg)
        _check_registration_config(checks, req, reg_cfg)
        _check_payment_config(checks, req, pay_cfg)
        _check_pay_only_inventory(checks, req, pay_cfg)
        _check_cpa(checks, req, pay_cfg)
        _check_team_system(checks, req, pay_cfg)
        _check_free_backfill_inventory(checks, req)

    blocking = [c for c in checks if c.get("blocking") and c.get("status") == "fail"]
    return {
        "ok": not blocking,
        "mode": req.get("mode"),
        "payment_kind": _payment_kind(req),
        "requires_registration": _requires_registration(req),
        "requires_email_otp": _requires_email_otp(req),
        "paths": {
            "pay_config": str(s.PAY_CONFIG_PATH),
            "reg_config": str(reg_path),
            "database": str(get_db().path),
        },
        "checks": checks,
        "blocking": blocking,
    }


def health_error_message(health: dict) -> str:
    blocking = health.get("blocking") or []
    if not blocking:
        return ""
    head = blocking[0].get("message") or "配置健康检查未通过"
    missing: list[str] = []
    for check in blocking:
        missing.extend(check.get("missing") or [])
    suffix = f"；缺: {', '.join(missing[:6])}" if missing else ""
    if len(missing) > 6:
        suffix += f" 等 {len(missing)} 项"
    return head + suffix
