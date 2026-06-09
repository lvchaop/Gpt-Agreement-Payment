#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import OrderedDict
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")


def compact_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=OrderedDict)


def final_cookie(state: dict[str, Any], name: str) -> str:
    value = (((state.get("finalState") or {}).get("cookies") or {}).get(name) or {}).get("value")
    if not value:
        raise ValueError(f"missing final cookie {name}")
    return value


def signature_from_create(create_body: dict[str, Any]) -> OrderedDict[str, Any]:
    return OrderedDict(
        [
            ("memberName", create_body.get("MemberName", "")),
            ("siteId", create_body.get("SiteId") or "00000000480728C5"),
            ("uiFlavor", "Host"),
            ("appId", create_body.get("SiteId") or "00000000480728C5"),
            ("birthdate", create_body.get("BirthDate", "")),
            ("firstName", create_body.get("FirstName", "")),
            ("lastName", create_body.get("LastName", "")),
            ("countryCode", create_body.get("Country", "")),
            ("verificationCode", create_body.get("VerificationCodeSlt", "")),
            ("deviceDetails", OrderedDict([("isRdm", create_body.get("IsRDM", False))])),
            ("action", "SignUp"),
        ]
    )


def human_metadata(px3: str, pxde: str, pxvid: str) -> OrderedDict[str, Any]:
    return OrderedDict([("riskProvider", "Human"), ("px3", px3), ("pxde", pxde), ("pxvid", pxvid)])


def build_initial_risk_verify(*, continuation_token: str, create_body: dict[str, Any], px3: str, pxde: str, pxvid: str) -> OrderedDict[str, Any]:
    return OrderedDict(
        [
            ("continuationToken", continuation_token),
            ("riskProviderMetadata", [human_metadata(px3, pxde, pxvid)]),
            ("msaRiskVerifySignature", signature_from_create(create_body)),
        ]
    )


def build_solution_risk_verify(*, continuation_token: str, px3: str, pxde: str, pxvid: str) -> OrderedDict[str, Any]:
    solution = OrderedDict([("challengeType", "HumanCaptcha"), ("px3", px3), ("pxde", pxde), ("pxvid", pxvid)])
    return OrderedDict(
        [
            ("continuationToken", continuation_token),
            ("challengeSolution", solution),
            ("riskProviderMetadata", [human_metadata(px3, pxde, pxvid)]),
        ]
    )


def diff_objects(expected: Any, actual: Any, path: str = "$") -> list[str]:
    diffs: list[str] = []
    if type(expected) is not type(actual):
        return [f"{path}: type {type(expected).__name__} != {type(actual).__name__}"]
    if isinstance(expected, dict):
        ek, ak = list(expected.keys()), list(actual.keys())
        if ek != ak:
            diffs.append(f"{path}: keys {ek} != {ak}")
        for key in expected.keys() & actual.keys():
            diffs.extend(diff_objects(expected[key], actual[key], f"{path}.{key}"))
    elif isinstance(expected, list):
        if len(expected) != len(actual):
            diffs.append(f"{path}: len {len(expected)} != {len(actual)}")
        for idx, (e, a) in enumerate(zip(expected, actual)):
            diffs.extend(diff_objects(e, a, f"{path}[{idx}]"))
    elif expected != actual:
        diffs.append(f"{path}: {expected!r} != {actual!r}")
    return diffs


def analyze(material_path: Path, state_path: Path) -> dict[str, Any]:
    material = load_json(material_path)
    state = load_json(state_path)
    risk_rows = material.get("riskVerify") or []
    create_rows = material.get("createAccount") or []
    if len(risk_rows) < 2:
        raise ValueError("need at least two riskVerify rows")
    if not create_rows:
        raise ValueError("need CreateAccount row")

    initial_runtime = risk_rows[0]["requestBody"]
    solution_runtime = risk_rows[1]["requestBody"]
    create_runtime = create_rows[0]["requestBody"]
    first_px = (initial_runtime.get("riskProviderMetadata") or [{}])[0]
    pxvid = final_cookie(state, "_pxvid")
    final_px3 = final_cookie(state, "_px3")
    final_pxde = final_cookie(state, "_pxde")

    initial_built = build_initial_risk_verify(
        continuation_token=initial_runtime["continuationToken"],
        create_body=create_runtime,
        px3=first_px["px3"],
        pxde=first_px["pxde"],
        pxvid=first_px["pxvid"],
    )
    solution_built = build_solution_risk_verify(
        continuation_token=(risk_rows[0]["responseBody"] or {})["continuationToken"],
        px3=final_px3,
        pxde=final_pxde,
        pxvid=pxvid,
    )

    create_built = OrderedDict(create_runtime)
    create_built["ContinuationToken"] = (risk_rows[1]["responseBody"] or {})["continuationToken"]

    checks = {
        "initialObjectMatch": initial_built == initial_runtime,
        "initialJsonMatch": compact_json(initial_built) == compact_json(initial_runtime),
        "solutionObjectMatch": solution_built == solution_runtime,
        "solutionJsonMatch": compact_json(solution_built) == compact_json(solution_runtime),
        "createContinuationMatch": create_built.get("ContinuationToken") == create_runtime.get("ContinuationToken"),
        "createObjectMatch": create_built == create_runtime,
        "createJsonMatch": compact_json(create_built) == compact_json(create_runtime),
    }
    return {
        "materialPath": str(material_path),
        "statePath": str(state_path),
        "checks": checks,
        "diffs": {
            "initial": diff_objects(initial_runtime, initial_built),
            "solution": diff_objects(solution_runtime, solution_built),
            "create": diff_objects(create_runtime, create_built),
        },
        "built": {
            "initialRiskVerify": initial_built,
            "solutionRiskVerify": solution_built,
            "createAccount": create_built,
        },
        "runtime": {
            "initialRiskVerify": initial_runtime,
            "solutionRiskVerify": solution_runtime,
            "createAccount": create_runtime,
        },
    }


def write_outputs(result: dict[str, Any], out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    base = Path(result["materialPath"]).name.removeprefix("risk_verify_material_").removesuffix(".json")
    json_path = out_dir / f"risk_verify_build_{base}.json"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [f"# risk/verify request build: {base}", "", f"material={result['materialPath']}", f"state={result['statePath']}", ""]
    lines.append("## checks")
    for key, value in result["checks"].items():
        lines.append(f"- {key}: {value}")
    lines.append("")
    lines.append("## diffs")
    for name, diffs in result["diffs"].items():
        lines.append(f"### {name}")
        if not diffs:
            lines.append("- none")
        else:
            for diff in diffs:
                lines.append(f"- {diff}")
    md_path = out_dir / f"risk_verify_build_{base}.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Build risk/verify and CreateAccount request bodies from collector state and verify against runtime.")
    parser.add_argument("risk_material", type=Path)
    parser.add_argument("--collector-state", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, default=REPO / "output/protocol_reverse/risk_verify_build")
    args = parser.parse_args()
    result = analyze(args.risk_material, args.collector_state)
    json_path, md_path = write_outputs(result, args.out_dir)
    print(json.dumps({"jsonPath": str(json_path), "mdPath": str(md_path), "checks": result["checks"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
