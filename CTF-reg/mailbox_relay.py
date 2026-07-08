"""Mailbox-to-KV relay for account-list mail sources.

This mirrors the Cloudflare Email Worker path:

  Outlook/Gmail mailbox -> local relay -> Cloudflare KV -> registration flow

The relay is scoped to one reserved account at a time. It never scans the whole
mailbox pool.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from cf_kv_otp_provider import CloudflareKVOtpProvider
from email_account_pool import EmailAccount
from graph_otp_provider import GraphOtpProvider
from imap_otp_provider import ImapOtpProvider


logger = logging.getLogger(__name__)


class MailboxRelay:
    def __init__(
        self,
        kv_provider: CloudflareKVOtpProvider,
        *,
        mark_seen: bool = False,
        kv_ttl: int = 600,
    ):
        self.kv_provider = kv_provider
        self.mark_seen = mark_seen
        self.kv_ttl = kv_ttl

    def relay_until_otp(
        self,
        account: EmailAccount,
        email_addr: str,
        *,
        timeout: int = 180,
        issued_after: Optional[float] = None,
    ) -> dict:
        """Poll one active mailbox until OTP, then write it to Cloudflare KV."""
        logger.info(
            "[mail-relay] watch active mailbox=%s provider=%s timeout=%ss",
            email_addr,
            account.provider,
            timeout,
        )
        graph_error: Exception | None = None
        match = None
        if self._prefer_graph(account):
            try:
                graph_provider = GraphOtpProvider(account, mark_seen=self.mark_seen)
                match = graph_provider.wait_for_otp_match(
                    email_addr,
                    timeout=timeout,
                    issued_after=issued_after,
                )
                logger.info(
                    "[mail-relay] Graph OTP ok email=%s uid=%s subject=%r",
                    email_addr,
                    match.uid,
                    match.subject[:80],
                )
            except Exception as e:
                graph_error = e
                logger.warning(
                    "[mail-relay] Graph failed, fallback IMAP email=%s error=%s",
                    email_addr,
                    e,
                )
        if match is None:
            provider = ImapOtpProvider(account, mark_seen=self.mark_seen)
            try:
                match = provider.wait_for_otp_match(
                    email_addr,
                    timeout=timeout,
                    issued_after=issued_after,
                )
            except Exception as e:
                if graph_error is not None:
                    raise RuntimeError(
                        f"Graph 和 IMAP 均未取到 OTP；graph_error={graph_error}; imap_error={e}"
                    ) from e
                raise
        payload = match.to_kv_payload()
        self.kv_provider.put_otp(
            email_addr,
            match.otp,
            metadata=payload,
            ttl=self.kv_ttl,
        )
        logger.info(
            "[mail-relay] wrote OTP to KV email=%s uid=%s subject=%r",
            email_addr,
            payload.get("uid", ""),
            str(payload.get("subject", ""))[:80],
        )
        return payload

    @staticmethod
    def _prefer_graph(account: EmailAccount) -> bool:
        fetch_protocol = (os.environ.get("MAIL_FETCH_PROTOCOL") or "auto").strip().lower()
        if fetch_protocol == "imap":
            return False
        provider = (account.provider or "").strip().lower()
        return provider == "outlook" and bool(account.access_token or account.refresh_token)
