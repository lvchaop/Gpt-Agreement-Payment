import shutil
import sys
import platform
from ._common import CheckResult, PreflightResult, aggregate


def check() -> PreflightResult:
    checks: list[CheckResult] = []

    # Python
    if sys.version_info >= (3, 10):
        checks.append(CheckResult(name="python", status="ok",
                                  message=f"Python {sys.version.split()[0]}"))
    else:
        checks.append(CheckResult(name="python", status="fail",
                                  message=f"Python {sys.version.split()[0]} < 3.10"))

    # Binaries
    for binary in ("camoufox",):
        path = shutil.which(binary)
        checks.append(CheckResult(
            name=binary,
            status="ok" if path else "fail",
            message=path or f"{binary} not found in PATH",
        ))
    xvfb_path = shutil.which("xvfb-run")
    if platform.system().lower() == "linux":
        xvfb_status = "ok" if xvfb_path else "fail"
        xvfb_message = xvfb_path or "xvfb-run not found in PATH"
    else:
        xvfb_status = "ok"
        xvfb_message = xvfb_path or "not needed on macOS/desktop"
    checks.append(CheckResult(name="xvfb-run", status=xvfb_status, message=xvfb_message))

    # Playwright import
    try:
        import playwright  # noqa: F401
        checks.append(CheckResult(name="playwright", status="ok",
                                  message="playwright importable"))
    except ImportError as e:
        checks.append(CheckResult(name="playwright", status="fail",
                                  message=str(e)))

    return aggregate(checks)
