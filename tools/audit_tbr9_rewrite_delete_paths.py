#!/usr/bin/env python3
from __future__ import annotations

import base64
import importlib.util
import json
import re
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
EXACT_CAPTCHA = REPO / "output/protocol_reverse/exact_source/captcha_ni109_4b399270.source.js"
CAPTCHA_BEAUTIFIED = REPO / "output/outlook_browser/js_static_analysis/captcha.beautified.js"
MAIN_BEAUTIFIED = REPO / "output/outlook_browser/js_static_analysis/main.beautified.js"
MAIN_MIN = REPO / "output/outlook_browser/js_probe/main.min.js"
DECODE_EXACT = REPO / "output/protocol_reverse/source_offsets/captcha_px561_remaining_fields_ni109_exact.json"
OUT_DIR = REPO / "output/protocol_reverse/source_offsets"

TARGET = "TBR9Ugl7emA="


def load_collector_helpers():
    spec = importlib.util.spec_from_file_location("map_px561_collector_handlers", REPO / "tools/map_px561_collector_handlers.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load map_px561_collector_handlers.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def b64_decode(value: str) -> str:
    return base64.b64decode(value + "=" * ((4 - len(value) % 4) % 4)).decode("latin1")


def line_slice(path: Path, start: int, end: int) -> list[dict[str, Any]]:
    lines = read(path).splitlines()
    return [
        {"line": line_no, "text": lines[line_no - 1]}
        for line_no in range(start, end + 1)
        if 1 <= line_no <= len(lines)
    ]


def regex_count(text: str, pattern: str) -> int:
    return len(re.findall(pattern, text))


def find_offsets(text: str, needle: str, limit: int = 20) -> list[int]:
    offsets: list[int] = []
    start = 0
    while True:
        pos = text.find(needle, start)
        if pos < 0:
            break
        offsets.append(pos)
        if len(offsets) >= limit:
            break
        start = pos + 1
    return offsets


def decode_main_keys() -> dict[str, str]:
    helper = load_collector_helpers()
    rotated, _ = helper.rotate_dc(helper.extract_array(read(MAIN_MIN), "Dc"))
    raw = lambda idx: helper.dc(rotated, idx)
    return {
        "GcDeletesFalseFlag_Cc_j_yc275": b64_decode(raw(275)),
        "jcDeletesFc_j_yc285": b64_decode(raw(285)),
        "jcWritesNcTo_yc221": raw(221),
        "jcActivityType_yc247": raw(247),
        "YcDeleteFirst_yc278": raw(278),
        "YcDeleteSecond_yc231": raw(231),
        "YcPx561Type_yc269": raw(269),
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    exact = read(EXACT_CAPTCHA)
    captcha_pretty = read(CAPTCHA_BEAUTIFIED)
    main_pretty = read(MAIN_BEAUTIFIED)
    decode_exact = json.loads(DECODE_EXACT.read_text(encoding="utf-8"))
    decoded_by_expr = {row["expr"]: row for row in decode_exact["records"]}
    main_keys = decode_main_keys()

    exact_counts = {
        "direct_tbr_assignment_expr": regex_count(exact, r"r\[t\(v\(-540,-543\)\)\]=_s\(\)"),
        "direct_succeeded_assignment_expr": regex_count(exact, r"r\[t\(v\(-541,-541\)\)\]=Ws\[t\(\"NQ\"\)\]\(n\)"),
        "direct_aeax_assignment_expr": regex_count(exact, r"r\[t\(\"FnM4CCwDASRmEyFT\"\)\]=Ws\[t\(\"Ng\"\)\]\(\)"),
        "fnm4_literal": exact.count("FnM4CCwDASRmEyFT"),
        "hgask_literal": exact.count("HGASKTZabC1xSx9T"),
        "literal_tbr_decoded_key": exact.count(TARGET),
        "literal_tbr_value_prefix": exact.count("Y@tvUUF@W"),
        "delete_keyword": exact.count("delete "),
    }
    pretty_counts = {
        "captcha_delete_keyword": captcha_pretty.count("delete "),
        "captcha_direct_tbr_assignment_line": find_offsets(captcha_pretty, "r[t(v(-540, -543))] = _s()"),
        "main_delete_keyword": main_pretty.count("delete "),
        "main_literal_tbr_decoded_key": main_pretty.count(TARGET),
        "main_literal_tbr_value_prefix": main_pretty.count("Y@tvUUF@W"),
    }

    candidate_delete_keys = {
        "captcha_D_pre_submit_delete": {
            "source": "captcha.beautified.js:11071 delete d[f(K(-158,-171))]",
            "decodedKeyFromPriorAudit": "TlJ/FAs7fSY=",
            "isTbr": False,
        },
        "main_Gc_delete": {
            "source": "main.beautified.js:2927 delete t[Cc]",
            "decodedKey": main_keys["GcDeletesFalseFlag_Cc_j_yc275"],
            "isTbr": main_keys["GcDeletesFalseFlag_Cc_j_yc275"] == TARGET,
        },
        "main_Yc_delete_first": {
            "source": "main.beautified.js:2996 delete e[F(278)]",
            "decodedKey": main_keys["YcDeleteFirst_yc278"],
            "isTbr": main_keys["YcDeleteFirst_yc278"] == TARGET,
        },
        "main_Yc_delete_second": {
            "source": "main.beautified.js:2996 delete e[F(231)]",
            "decodedKey": main_keys["YcDeleteSecond_yc231"],
            "isTbr": main_keys["YcDeleteSecond_yc231"] == TARGET,
        },
        "main_jc_delete_fc": {
            "source": "main.beautified.js:3048 delete t[Fc]",
            "decodedKey": main_keys["jcDeletesFc_j_yc285"],
            "isTbr": main_keys["jcDeletesFc_j_yc285"] == TARGET,
        },
    }

    result = {
        "inputs": {
            "exactCaptcha": str(EXACT_CAPTCHA),
            "captchaBeautified": str(CAPTCHA_BEAUTIFIED),
            "mainBeautified": str(MAIN_BEAUTIFIED),
            "decodeExact": str(DECODE_EXACT),
        },
        "exactDecodedRecords": decoded_by_expr,
        "exactSourceCounts": exact_counts,
        "beautifiedCounts": pretty_counts,
        "mainDecodedDeleteAndRewriteKeys": main_keys,
        "candidateDeleteKeys": candidate_delete_keys,
        "sourceSnippets": {
            "captcha_D_Ts_11066_11099": line_slice(CAPTCHA_BEAUTIFIED, 11066, 11099),
            "main_Gc_Yc_jc_2924_3049": line_slice(MAIN_BEAUTIFIED, 2924, 3049),
        },
        "findings": [
            "Exact ni109 captcha source contains exactly one direct TBR9 assignment expression in D/Ts: r[t(v(-540,-543))]=_s().",
            "Exact ni109 captcha source contains exactly one adjacent succeeded assignment expression: r[t(v(-541,-541))]=Ws[t(\"NQ\")](n).",
            "The audited captcha D pre-submit delete targets TlJ/FAs7fSY=, not TBR9Ugl7emA=.",
            "The audited main Gc/Yc/jc delete paths target PX11719, PX12616, PX12617, and PX755, not TBR9Ugl7emA=.",
            "No literal TBR9Ugl7emA= or final TBR9 value prefix appears in exact captcha source or main beautified source.",
        ],
        "conclusion": "The obvious exact-source delete/rewrite sites around captcha D/Ts and main Yc/jc do not explain the final 127-byte TBR9 value. The remaining gap is now an alternate producer or a non-obvious computed rewrite not covered by simple decoded delete-key auditing.",
        "nextEvidenceTargets": [
            "Search for computed object merge/rewrite paths after D/Ts but before Rc/Yc that can assign decoded keys without literal TBR9.",
            "Capture pre-Yc object and tf entry in a labeled observation sample to determine whether the 127-byte TBR9 exists before Yc or appears after queueing.",
            "If pre-Yc lacks TBR9 but tf entry has it, audit Rc/ds queue mutation and any activity normalizers between Rc and tf.",
        ],
    }

    json_path = OUT_DIR / "tbr9_rewrite_delete_paths_audit.json"
    md_path = OUT_DIR / "tbr9_rewrite_delete_paths_audit.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# TBR9 rewrite/delete path audit",
        "",
        "## Exact source counts",
        "",
    ]
    for key, value in exact_counts.items():
        lines.append(f"- {key}: `{value}`")
    lines += [
        "",
        "## Candidate delete keys",
        "",
        "| site | decoded key | is TBR9 | source |",
        "|---|---|---:|---|",
    ]
    for site, row in candidate_delete_keys.items():
        lines.append(f"| `{site}` | `{row.get('decodedKey') or row.get('decodedKeyFromPriorAudit')}` | `{row['isTbr']}` | {row['source']} |")
    lines += [
        "",
        "## Findings",
        "",
    ]
    lines += [f"- {finding}" for finding in result["findings"]]
    lines += [
        "",
        "## Conclusion",
        "",
        result["conclusion"],
        "",
        "## Next evidence targets",
        "",
    ]
    lines += [f"- {target}" for target in result["nextEvidenceTargets"]]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps({"json": str(json_path), "md": str(md_path)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
