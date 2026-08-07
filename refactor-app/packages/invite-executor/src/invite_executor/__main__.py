from __future__ import annotations

import uvicorn

from invite_executor.api import create_app
from invite_executor.settings import InviteExecutorSettings


def main() -> None:
    settings = InviteExecutorSettings()
    uvicorn.run(
        create_app(settings),
        host=settings.host,
        port=settings.port,
        workers=1,
        log_level=settings.log_level,
    )


if __name__ == "__main__":
    main()
