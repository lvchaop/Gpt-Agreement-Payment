#!/usr/bin/env python3
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "output/protocol_reverse/source_offsets"
OUT_DIR.mkdir(parents=True, exist_ok=True)

MAIN = ROOT / "output/outlook_browser/js_static_analysis/main.beautified.js"
CAPTCHA = ROOT / "output/outlook_browser/js_static_analysis/captcha.beautified.js"
TS_AUDIT = OUT_DIR / "px561_ts_key_layer_audit.json"


BRIDGE_STEPS = [
    {
        "id": "main_Zc_registers_bridge",
        "file": MAIN,
        "lineStart": 3032,
        "lineEnd": 3041,
        "evidence": "Zc() obtains Lc()[PX762], assigns callbacks, then calls f($c,t,e,n,r).",
        "decoded": {
            "yc(277)": "PX762",
            "yc(220)": "PX763 -> jc",
            "yc(249)": "PX1078 -> Oc",
            "yc(262)": "PX1200 -> Kc",
            "yc(242)": "PX1145 -> nu",
        },
    },
    {
        "id": "captcha_Fu_visible_registration",
        "file": CAPTCHA,
        "lineStart": 4463,
        "lineEnd": 4477,
        "evidence": "Fu(r) assigns window[Su()] object with visible decoded key slice, then calls r.apply(this,args).",
        "decoded": {
            "t(v(-543,-542))": "slice",
        },
        "boundary": "This does not by itself prove PX762; PX762 bridge is proven from main Zc runtime expectation plus later window[Su()] callback usage, not from this visible Fu key.",
    },
    {
        "id": "captcha_Ls_stores_callback_state",
        "file": CAPTCHA,
        "lineStart": 8148,
        "lineEnd": 8156,
        "evidence": "Ls.PlqQBA stores jz/fakeToken/D/startTime and later uses D as submit callback.",
    },
    {
        "id": "captcha_D_prepares_r",
        "file": CAPTCHA,
        "lineStart": 11046,
        "lineEnd": 11071,
        "evidence": "D(r,n,t) merges worker fields, J(r) geometry/POW fields, and optionally emits W0cqQR4rLnA= through window[Su()][PX1200].",
        "decoded": {
            "K(-173,-184)": "PX763",
            "K(-166,-160)": "PX1200",
            "K(-169,-188)": "W0cqQR4rLnA=",
            "K(-174,-196)": "FU1kS1AhYX4=",
            "K(-165,-176)": "usedWebWorkers",
        },
    },
    {
        "id": "captcha_Ts_adds_success_fields_and_calls_Ou",
        "file": CAPTCHA,
        "lineStart": 11073,
        "lineEnd": 11099,
        "evidence": "Ts callback mutates r, then Ou() returns Yu and i(PX561,r) sends the same r object to main callback.",
        "decoded": {
            "c(439,441)": "PX561",
            "c(413,425)": "PX763",
            "\"B25ORlo\"": "PX764",
        },
    },
    {
        "id": "main_dollar_c_finalizes_px561",
        "file": MAIN,
        "lineStart": 3078,
        "lineEnd": 3080,
        "evidence": "$c(t,e) calls Rc(t,Yc(e,t)); for PX561 this copies/flattens e into final collector activity.",
    },
    {
        "id": "main_ds_queues_final_activity",
        "file": MAIN,
        "lineStart": 3455,
        "lineEnd": 3468,
        "evidence": "ds(t,e) appends {t,d:e,ts} into activity queue ss/ls; this is the final serialized activity source.",
    },
]


def lines(path: Path, start: int, end: int) -> str:
    arr = path.read_text(errors="replace").splitlines()
    return "\n".join(f"{i:5d}: {arr[i - 1]}" for i in range(start, min(end, len(arr)) + 1))


def main() -> None:
    ts = json.loads(TS_AUDIT.read_text())
    records = []
    for step in BRIDGE_STEPS:
        rec = dict(step)
        rec["file"] = str(step["file"])
        rec["snippet"] = lines(step["file"], step["lineStart"], step["lineEnd"])
        records.append(rec)

    result = {
        "inputs": {
            "mainBeautified": str(MAIN),
            "captchaBeautified": str(CAPTCHA),
            "tsKeyLayerAudit": str(TS_AUDIT),
        },
        "bridgeSteps": records,
        "tsAuditConclusions": ts.get("conclusions", []),
        "proven": [
            "main Zc expects window[Su()][PX762] and passes $c as collector callback.",
            "captcha Ts callback mutates r then calls i(PX561,r), where i is Ou() / Yu.",
            "main $c passes the received object to Yc(e,PX561), and Yc copies/flattens into final activity.",
        ],
        "notProven": [
            "Fu() visible key decodes to slice, so the exact assignment path from Fu() to PX762 remains unresolved.",
            "The producer of final key fyNOZTpPQF4= is still not located.",
            "The producer or overwrite path of TBR9Ugl7emA= long string is still not located.",
        ],
    }

    json_path = OUT_DIR / "px561_callback_bridge_audit.json"
    md_path = OUT_DIR / "px561_callback_bridge_audit.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2))

    out = [
        "# PX561 callback bridge audit",
        "",
        f"- main: `{MAIN}`",
        f"- captcha: `{CAPTCHA}`",
        f"- depends on: `{TS_AUDIT}`",
        "",
        "## Bridge steps",
        "",
    ]
    for rec in records:
        out += [
            f"### {rec['id']}",
            "",
            f"- file: `{rec['file']}`",
            f"- lines: `{rec['lineStart']}..{rec['lineEnd']}`",
            f"- evidence: {rec['evidence']}",
        ]
        if rec.get("decoded"):
            out.append("- decoded:")
            for k, v in rec["decoded"].items():
                out.append(f"  - `{k}` => `{v}`")
        if rec.get("boundary"):
            out.append(f"- boundary: {rec['boundary']}")
        out += ["", "```js", rec["snippet"], "```", ""]

    out += ["## Proven", ""]
    out += [f"- {x}" for x in result["proven"]]
    out += ["", "## Not proven / next evidence gap", ""]
    out += [f"- {x}" for x in result["notProven"]]
    md_path.write_text("\n".join(out) + "\n")
    print(json.dumps({"json": str(json_path), "md": str(md_path)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
