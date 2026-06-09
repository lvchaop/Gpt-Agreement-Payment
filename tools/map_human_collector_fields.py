#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
OUT = REPO / "output/protocol_reverse/collector_field_map"


FIELDS = [
    {
        "field": "payload",
        "status": "implemented",
        "runtime_source": "tf.payload hook: data.activities + data.meta",
        "static_evidence": [
            "main.beautified.js:4807-4837 tf mutates activities, builds meta, calls Vs, emits payload",
            "main.beautified.js:4789-4803 zl/Kl unicode-marker helpers",
        ],
        "builder": "tools/build_human_collector_request.mjs: ut + Jt + Vs + marker",
    },
    {
        "field": "pc",
        "status": "implemented",
        "runtime_source": "tf.payload hook: data.activities + meta.cu/tag + ft",
        "static_evidence": [
            "main.beautified.js:4826-4828 h = Jt(ut(t), [po(), tag, ft].join(':'))",
            "main.beautified.js:4839 h && p.push(Rr + h)",
        ],
        "builder": "tools/build_human_collector_request.mjs: jt(ut(activities), [cu, tag, ft].join(':'))",
    },
    {
        "field": "appId/tag/uuid/ft/seq/en",
        "status": "implemented_with_runtime_ft_sequence",
        "runtime_source": "tf.payload hook meta + runtime request ft/seq/en",
        "static_evidence": [
            "main.beautified.js:406-408 gt='YjIYfyxJHRR9', yt='369', bt='PXzC5j78di'",
            "main.beautified.js:414-415 Et() returns app id",
            "main.beautified.js:422-423 Tt() returns tag",
            "main.beautified.js:1593-1595 po() returns or creates ClientUuid",
            "main.beautified.js:4804-4805 ql='NTA', $l=0",
            "main.beautified.js:4837 form order includes payload/appId/tag/uuid/ft/seq/en",
        ],
        "builder": "tools/build_human_collector_request.mjs",
    },
    {
        "field": "marker",
        "status": "partially_implemented",
        "runtime_source": "hook.marker when available; otherwise inverse from observed payload",
        "static_evidence": [
            "main.beautified.js:3566 ne(J(Qi() || t(118)), 10) in Vs marker path",
            "main.beautified.js:2675-2677 Qi() returns Jo",
            "main.beautified.js:4701-4702 Yl(t) sets Jo=t",
            "main.beautified.js:4486-4488 handler oIIoIoII maps to Yl",
        ],
        "builder": "tools/build_human_collector_request.mjs: extractMarkerFromPayload fallback",
        "gap": "Need independent live producer for Jo/Qi marker without observed payload.",
    },
    {
        "field": "cs",
        "status": "mapped_not_independent",
        "runtime_source": "runtime request currently reused by builder",
        "static_evidence": [
            "main.beautified.js:2666-2667 Li() returns Yo",
            "main.beautified.js:4482-4484 IoIIII(t) sets Yo=t and clears so via vo(null) if changed",
            "main.beautified.js:4826 f = Li()",
            "main.beautified.js:4839 f && p.push(Tr + f)",
        ],
        "gap": "Need derive Yo from decoded collector handler IoIIII and replay state.",
    },
    {
        "field": "sid",
        "status": "mapped_not_independent",
        "runtime_source": "runtime request currently reused by builder",
        "static_evidence": [
            "main.beautified.js:4840 g = e[fn]()",
            "main.beautified.js:4841 y = Kl(Qi())",
            "main.beautified.js:4842 (g || y) && p.push(Ar + (g || po()) + y)",
            "main.beautified.js:1917-1921 Vi() returns cached pxsid",
            "main.beautified.js:2675-2677 Qi() returns Jo",
            "main.beautified.js:4701-4702 Yl(t) sets Jo=t",
        ],
        "gap": "Need independently reproduce e[fn]() fallback and Kl(Qi()) suffix in live protocol.",
    },
    {
        "field": "p1",
        "status": "mapped_not_independent",
        "runtime_source": "runtime request currently reused by builder",
        "static_evidence": [
            "main.beautified.js:2640-2648 Gi(e) extracts p1..p10 from pxParams or window _pxParamN",
            "main.beautified.js:8602-8611 e[hn]() returns encoded np params",
        ],
        "gap": "Need map hn/Gi output to exact p1 from iframe session_id / px params.",
    },
    {
        "field": "vid",
        "status": "mapped_not_independent",
        "runtime_source": "runtime request currently reused by builder",
        "static_evidence": [
            "main.beautified.js:426-428 Rt(t) sets mt",
            "main.beautified.js:457-458 Ct() returns mt",
            "main.beautified.js:4404-4411 IooIoo handler sets Rt/Oi/Wn for _pxvid",
            "main.beautified.js:4844 Ct() && p.push(Mr + Ct())",
        ],
        "gap": "Need feed decoded IooIoo handler into protocol state before request build.",
    },
    {
        "field": "cts",
        "status": "mapped_not_independent",
        "runtime_source": "runtime request currently reused by builder",
        "static_evidence": [
            "main.beautified.js:1901-1903 Bi(t,e,n) sets Fo=t and Wn(li,...), li=pxcts",
            "main.beautified.js:4523-4525 oIIooIIo handler calls Bi(t,e)",
            "main.beautified.js:4850 Fo && p.push(Br + Fo)",
        ],
        "gap": "Need feed decoded oIIooIIo handler into protocol state before request build.",
    },
    {
        "field": "rsc",
        "status": "mapped_not_independent",
        "runtime_source": "runtime request currently reused by builder",
        "static_evidence": [
            "main.beautified.js:1053-1071 Xr decodes to rsc= prefix",
            "main.beautified.js:8568-8601 beacon/no-cors branch calls tf(...).join('&')",
            "main.beautified.js:8688-8694 retry branch calls ep(t)",
        ],
        "gap": "Need fully map Fv(t) appending rsc counter and noCors/beacon routing.",
    },
    {
        "field": "hid",
        "status": "mapped_not_independent",
        "runtime_source": "not present in current 12 normal collector bodies; mapped for future beacon/success bodies",
        "static_evidence": [
            "main.beautified.js:4327-4328 mobile data Sl() can set hid via Bi and Co",
            "main.beautified.js:4850 Co && p.push(Nr + Co)",
        ],
        "gap": "Need sample where hid appears in collector body to validate.",
    },
]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    payload = {"fields": FIELDS}
    json_path = OUT / "collector_field_map.json"
    md_path = OUT / "collector_field_map.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = ["# HUMAN collector field map", ""]
    lines.append("| field | status | runtime source | static evidence | gap |")
    lines.append("|---|---|---|---|---|")
    for item in FIELDS:
        evidence = "<br>".join(item.get("static_evidence", []))
        lines.append(
            f"| {item['field']} | {item['status']} | {item['runtime_source']} | {evidence} | {item.get('gap', '')} |"
        )
    lines.append("")
    lines.append("## evidence boundary")
    lines.append("- This file is a static/runtime field map, not an end-to-end protocol success proof.")
    lines.append("- `implemented` means current local tool can reproduce observed field values from hook/static inputs.")
    lines.append("- `mapped_not_independent` means static producer/consumer locations are identified, but current body builder still reuses runtime request values.")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"jsonPath": str(json_path), "mdPath": str(md_path), "fieldCount": len(FIELDS)}, indent=2))


if __name__ == "__main__":
    main()
