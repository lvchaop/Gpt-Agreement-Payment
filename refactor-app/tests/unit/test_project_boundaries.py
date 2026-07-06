from __future__ import annotations

from pathlib import Path


def test_runtime_code_does_not_reference_old_project_or_sqlite() -> None:
    root = Path(__file__).resolve().parents[2]
    source_files = sorted((root / "src").rglob("*.py"))

    forbidden_fragments = [
        "sqlite",
        "CTF-reg",
        "CTF-pay",
        "webui",
        "pipeline.py",
        "sys.path",
    ]

    violations: list[str] = []
    for path in source_files:
        text = path.read_text()
        for fragment in forbidden_fragments:
            if fragment in text:
                violations.append(f"{path.relative_to(root)} contains {fragment!r}")

    assert violations == []


def test_runtime_dependencies_do_not_include_stateful_middleware() -> None:
    root = Path(__file__).resolve().parents[2]
    pyproject = (root / "pyproject.toml").read_text()

    forbidden_dependencies = [
        "redis",
        "celery",
        "rabbitmq",
        "kafka",
        "nats",
        "sqlite",
    ]

    violations = [dependency for dependency in forbidden_dependencies if dependency in pyproject]

    assert violations == []
