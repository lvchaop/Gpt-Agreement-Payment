from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any


class StablePlusCheckoutSubmitter:
    """Submit one hosted Checkout exactly once and verify its terminal state."""

    _READY_PHASES = {"ready"}
    _FAILED_PHASES = {"error", "failed", "load_error", "destroyed", "submit_failed"}

    def __init__(
        self,
        page: Any,
        *,
        timeout_s: float,
        result_poll_attempts: int,
        result_poll_interval_s: float,
        challenge_callback: Callable[[dict[str, Any]], None] | None,
        captcha_solver: Callable[[dict[str, Any]], dict[str, Any]] | None,
        runtime: Any,
    ) -> None:
        self.page = page
        self.timeout_s = max(1.0, float(timeout_s))
        self.result_poll_attempts = max(1, int(result_poll_attempts))
        self.result_poll_interval_s = max(0.0, float(result_poll_interval_s))
        self.challenge_callback = challenge_callback
        self.captcha_solver = captcha_solver
        self.runtime = runtime

        self.capture = runtime._CheckoutChallengeCapture(page)
        self.challenge_notified = False
        self.challenge_attempts = 0
        self.solved_challenges: set[str] = set()
        self.last_solver_error = ""
        self.last_solver_task_id = ""
        self.last_verification: dict[str, Any] | None = None

        self.detected: dict[str, Any] = {}
        self.provider = ""
        self.state_script = ""
        self.submit_script = ""
        self.submit_started = False
        self.navigation_interruptions = 0
        self.last_navigation_url = ""

    def _notify_challenge(self) -> None:
        if self.challenge_notified or not callable(self.challenge_callback):
            return
        snapshot = self.capture.snapshot()
        if not snapshot["challenge_detected"]:
            return
        self.challenge_notified = True
        try:
            self.challenge_callback(snapshot)
        except Exception:
            pass

    def _configure(self) -> None:
        detected = self.page.evaluate(self.runtime.READ_PLUS_CHECKOUT_PROVIDER_SCRIPT)
        if not isinstance(detected, dict):
            raise self.runtime.PlusCheckoutPluginError(
                "plus_checkout_plugin_provider_result_invalid"
            )
        provider = str(detected.get("provider") or "").strip().lower()
        config = self.runtime._PLUS_CHECKOUT_PLUGIN_CONFIG.get(provider)
        if config is None:
            raise self.runtime.PlusCheckoutPluginError(
                "plus_checkout_plugin_provider_unsupported: "
                + str(detected.get("pathname") or "")
            )

        self.detected = detected
        self.provider = provider
        self.state_script = self.runtime._plugin_state_script(
            state_key=str(config["state_key"]),
            host_id=str(config["host_id"]),
        )
        self.submit_script = self.runtime._plugin_submit_script(
            state_key=str(config["state_key"]),
            host_id=str(config["host_id"]),
        )
        if callable(self.captcha_solver):
            self.page.evaluate(self.runtime.INSTALL_PLUS_CHECKOUT_CAPTCHA_BRIDGE_SCRIPT)
        self.page.evaluate(self.runtime._plugin_mount_expression(str(config["script"])))
        self._notify_challenge()

    def _wait_ready(self) -> dict[str, Any]:
        deadline = time.monotonic() + self.timeout_s
        while True:
            try:
                state = self.runtime._read_plugin_state(self.page, self.state_script)
            except Exception as error:
                if not self.runtime._is_checkout_navigation_context_error(error):
                    raise
                if time.monotonic() >= deadline:
                    raise self.runtime.PlusCheckoutPluginError(
                        "plus_checkout_plugin_ready_navigation_timeout"
                    ) from error
                time.sleep(0.1)
                continue

            self._notify_challenge()
            phase = str(state.get("phase") or "").strip().lower()
            if phase in self._READY_PHASES:
                if state.get("panel_visible") is not True:
                    raise self.runtime.PlusCheckoutPluginError(
                        "plus_checkout_plugin_panel_missing"
                    )
                return state
            if phase in self._FAILED_PHASES:
                detail = str(state.get("last_error") or phase)
                raise self.runtime.PlusCheckoutPluginError(
                    f"plus_checkout_plugin_{phase}: {detail}"
                )
            if time.monotonic() >= deadline:
                raise self.runtime.PlusCheckoutPluginError(
                    f"plus_checkout_plugin_ready_timeout: phase={phase or 'unknown'}"
                )
            time.sleep(0.1)

    def _record_navigation_interruption(self) -> None:
        self.navigation_interruptions += 1
        self.last_navigation_url = self.runtime._page_url(self.page)

    def _start_once(self, ready_state: dict[str, Any]) -> bool:
        if self.submit_started:
            raise self.runtime.PlusCheckoutPluginError(
                "plus_checkout_duplicate_submit_blocked"
            )
        self.submit_started = True
        try:
            started = self.page.evaluate(self.submit_script)
        except Exception as error:
            if not self.runtime._is_checkout_navigation_context_error(error):
                raise
            self._record_navigation_interruption()
            return False
        if started is not True:
            raise self.runtime.PlusCheckoutPluginError(
                "plus_checkout_plugin_submit_unavailable: "
                + self.runtime._compact_json(ready_state)
            )
        return True

    def _read_state(self, previous: dict[str, Any]) -> dict[str, Any]:
        current_url = self.runtime._page_url(self.page)
        if self.runtime._is_plus_checkout_success_url(current_url):
            return {**previous, "phase": "submitted", "redirect_url": current_url}
        try:
            state = self.runtime._read_plugin_state(self.page, self.state_script)
        except Exception as error:
            if not self.runtime._is_checkout_navigation_context_error(error):
                raise
            self._record_navigation_interruption()
            return {
                **previous,
                "phase": "execution_context_lost",
                "navigation_error": str(error)[:500],
            }
        self._notify_challenge()
        return self.runtime._hydrate_checkout_challenge_state(
            state,
            challenge_capture=self.capture,
            page_url=current_url,
        )

    def _solve_challenge(self, state: dict[str, Any]) -> dict[str, Any] | None:
        try:
            outcome = self.runtime._maybe_solve_checkout_challenge(
                page=self.page,
                state=state,
                challenge_capture=self.capture,
                captcha_solver=self.captcha_solver,
                solved_challenges=self.solved_challenges,
            )
        except self.runtime.PlusCheckoutPluginError as error:
            detail = str(error)
            if not detail.startswith("plus_checkout_captcha_"):
                raise
            self.last_solver_error = detail
            raise self.runtime.PlusCheckoutPluginError(
                f"{detail}; challenge={self.runtime._compact_json(state.get('challenge'))}"
            ) from error
        if not outcome:
            return None

        self.challenge_attempts += 1
        self.last_solver_task_id = str(outcome.get("solver_task_id") or "")
        verification = outcome.get("verification")
        if isinstance(verification, dict):
            self.last_verification = verification
        return outcome

    def _poll_terminal(self, state: dict[str, Any]) -> dict[str, Any]:
        payment_result = self.runtime.poll_plus_checkout_result(
            self.page,
            provider=self.provider,
            checkout_session_id=str(self.detected.get("checkout_session_id") or ""),
            checkout_confirm=state.get("checkout_confirm"),
            max_attempts=self.result_poll_attempts,
            interval_s=self.result_poll_interval_s,
        )
        payment_state = str(payment_result.get("state") or "").strip().lower()
        if payment_state != "succeeded":
            raise self.runtime.PlusCheckoutPluginError(
                "plus_checkout_terminal_state_not_succeeded: "
                + self.runtime._compact_json(payment_result)
            )
        return payment_result

    def _completed(
        self,
        state: dict[str, Any],
        *,
        payment_result: dict[str, Any],
    ) -> dict[str, Any]:
        result = {
            key: value
            for key, value in state.items()
            if key not in {"panel_visible", "default_payment_method_id", "last_error"}
        }
        result["phase"] = "submitted"
        result["payment_result"] = payment_result
        result["submit_attempts"] = 1
        result["challenge_attempts"] = self.challenge_attempts
        current_url = self.runtime._page_url(self.page)
        if self.runtime._is_plus_checkout_success_url(current_url):
            result["redirect_url"] = current_url
        if self.last_solver_error:
            result["challenge_solver_error"] = self.last_solver_error
        if self.last_solver_task_id:
            result["challenge_solver_task_id"] = self.last_solver_task_id
        if self.navigation_interruptions:
            result["submit_navigation_interrupted"] = self.navigation_interruptions
            result["submit_navigation_url"] = self.last_navigation_url
        return result

    def _finish_from_terminal_poll(self, state: dict[str, Any]) -> dict[str, Any]:
        return self._completed(state, payment_result=self._poll_terminal(state))

    def _wait_terminal(self, ready_state: dict[str, Any]) -> dict[str, Any]:
        start_returned = self._start_once(ready_state)
        if not start_returned:
            return self._finish_from_terminal_poll(ready_state)

        deadline = time.monotonic() + self.timeout_s
        last_state = dict(ready_state)
        while True:
            state = self._read_state(last_state)
            phase = str(state.get("phase") or "").strip().lower()
            if phase != "missing":
                last_state = dict(state)

            if phase in {"submitted", "execution_context_lost"}:
                return self._finish_from_terminal_poll(last_state)

            outcome = self._solve_challenge(state)
            if outcome:
                verification = outcome.get("verification")
                injection = outcome.get("injection")
                if isinstance(verification, dict):
                    return self._finish_from_terminal_poll(last_state)
                if isinstance(injection, dict) and injection.get("navigation_interrupted"):
                    return self._finish_from_terminal_poll(last_state)
                # Token injection continues the original Checkout confirmation.
                # It never starts a second confirmation.
                time.sleep(0.1)
                continue

            if phase in self._FAILED_PHASES:
                if self.challenge_attempts:
                    try:
                        return self._finish_from_terminal_poll(last_state)
                    except self.runtime.PlusCheckoutPluginError as poll_error:
                        detail = str(state.get("last_error") or phase)
                        raise self.runtime.PlusCheckoutPluginError(
                            f"plus_checkout_plugin_{phase}: {detail}; "
                            f"terminal_poll={poll_error}; state="
                            + self.runtime._compact_json(state)
                        ) from poll_error
                detail = str(state.get("last_error") or phase)
                raise self.runtime.PlusCheckoutPluginError(
                    f"plus_checkout_plugin_{phase}: {detail}; state="
                    + self.runtime._compact_json(state)
                )

            if time.monotonic() >= deadline:
                try:
                    return self._finish_from_terminal_poll(last_state)
                except self.runtime.PlusCheckoutPluginError as poll_error:
                    raise self.runtime.PlusCheckoutPluginError(
                        "plus_checkout_plugin_submit_timeout: "
                        + self.runtime._compact_json(last_state)
                        + f"; terminal_poll={poll_error}"
                    ) from poll_error
            time.sleep(0.1)

    def run(self) -> dict[str, Any]:
        self.capture.install()
        try:
            self._configure()
            result = self._wait_terminal(self._wait_ready())
            return {
                "provider": self.provider,
                "checkout_session_id": str(
                    self.detected.get("checkout_session_id") or ""
                ),
                **result,
                **self.capture.snapshot(),
            }
        except self.runtime.PlusCheckoutPluginError as error:
            challenge = self.capture.snapshot()
            if challenge["challenge_detected"]:
                error.args = (
                    f"{error} [challenge_detected=true "
                    f"kinds={','.join(challenge['challenge_kinds'])} "
                    f"requests={challenge['challenge_request_count']}]",
                )
            raise
        finally:
            self.capture.close()


def submit_plus_checkout_stably(
    page: Any,
    *,
    timeout_s: float,
    result_poll_attempts: int,
    result_poll_interval_s: float,
    challenge_callback: Callable[[dict[str, Any]], None] | None,
    captcha_solver: Callable[[dict[str, Any]], dict[str, Any]] | None,
    runtime: Any,
) -> dict[str, Any]:
    return StablePlusCheckoutSubmitter(
        page,
        timeout_s=timeout_s,
        result_poll_attempts=result_poll_attempts,
        result_poll_interval_s=result_poll_interval_s,
        challenge_callback=challenge_callback,
        captcha_solver=captcha_solver,
        runtime=runtime,
    ).run()


__all__ = ["StablePlusCheckoutSubmitter", "submit_plus_checkout_stably"]
