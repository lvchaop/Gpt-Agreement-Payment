#!/usr/bin/env node
import fs from "fs";
import path from "path";

const repo = "/Users/chaopenglv/data/me/Gpt-Agreement-Payment";
const outDir = path.join(repo, "output/outlook_browser/js_static_analysis/string_decode");
fs.mkdirSync(outDir, { recursive: true });

function atobCompat(input) {
  return Buffer.from(String(input).replace(/[=]+$/, ""), "base64").toString("binary");
}

function decodeUriBase64(input) {
  const raw = decodeCustomBase64(input, "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789+/=");
  let encoded = "";
  for (let i = 0; i < raw.length; i += 1) {
    encoded += "%" + ("00" + raw.charCodeAt(i).toString(16)).slice(-2);
  }
  return decodeURIComponent(encoded);
}

function decodeCustomBase64(input, alphabet) {
  const r = String(input);
  let n;
  let u;
  let t = "";
  let e = 0;
  let f = 0;
  while ((u = r.charAt(f++))) {
    const idx = alphabet.indexOf(u);
    if (~idx) {
      n = e % 4 ? 64 * n + idx : idx;
      if (e++ % 4) t += String.fromCharCode(255 & (n >> ((-2 * e) & 6)));
    }
  }
  return t;
}

function topU(input) {
  const raw = atobCompat(input);
  const key = "W6ypnhT";
  let out = "";
  for (let i = 0; i < raw.length; i += 1) {
    out += String.fromCharCode(key.charCodeAt(i % key.length) ^ raw.charCodeAt(i));
  }
  return out;
}

function extractArrayAfter(source, functionName, nearOffset = 0) {
  const idx = source.indexOf(`function ${functionName}`, nearOffset);
  if (idx < 0) throw new Error(`function not found: ${functionName}`);
  const arrStart = source.indexOf("[", idx);
  if (arrStart < 0) throw new Error(`array start not found: ${functionName}`);
  let i = arrStart;
  let inString = false;
  let quote = "";
  let esc = false;
  let depth = 0;
  for (; i < source.length; i += 1) {
    const ch = source[i];
    if (inString) {
      if (esc) esc = false;
      else if (ch === "\\") esc = true;
      else if (ch === quote) inString = false;
      continue;
    }
    if (ch === '"' || ch === "'") {
      inString = true;
      quote = ch;
      continue;
    }
    if (ch === "[") depth += 1;
    if (ch === "]") {
      depth -= 1;
      if (depth === 0) {
        const literal = source.slice(arrStart, i + 1);
        return { idx, arrStart, arrEnd: i + 1, values: Function(`return ${literal}`)() };
      }
    }
  }
  throw new Error(`array end not found: ${functionName}`);
}

function rotateCt(values) {
  const arr = values.slice();
  function ot(n) {
    let v = arr[n - 323];
    return decodeUriBase64(v);
  }
  function u(r, n) {
    return ot(n - -281);
  }
  let rotations = 0;
  for (;;) {
    try {
      const expr =
        -parseInt(u(-1, 69)) / 1 * (parseInt(u(228, 152)) / 2) +
        -parseInt(u(120, 138)) / 3 +
        -parseInt(u(138, 187)) / 4 +
        parseInt(u(123, 131)) / 5 +
        -parseInt(u(192, 179)) / 6 * (-parseInt(u(191, 174)) / 7) +
        -parseInt(u(100, 70)) / 8 +
        -parseInt(u(149, 162)) / 9 * (-parseInt(u(118, 62)) / 10);
      if (expr === 393305) break;
      arr.push(arr.shift());
      rotations += 1;
      if (rotations > values.length * 3) throw new Error("ct rotation did not converge");
    } catch {
      arr.push(arr.shift());
      rotations += 1;
      if (rotations > values.length * 3) throw new Error("ct rotation did not converge after catch");
    }
  }
  return { arr, rotations };
}

function makeOt(arr) {
  return function ot(n) {
    return decodeUriBase64(arr[n - 323]);
  };
}

function main() {
  const captchaPath = path.join(repo, "output/outlook_browser/js_probe/captcha.js");
  const source = fs.readFileSync(captchaPath, "utf8");
  const ct = extractArrayAfter(source, "ct", 280000);
  const rotated = rotateCt(ct.values);
  const ot = makeOt(rotated.arr);
  // Source form is `return ot(r- -7,n)`: subtracting negative 7 means r + 7.
  const Rt = (r) => ot(r + 7);
  const e = (r) => Rt(r - 705);

  const zeroToken = e(1095);
  const nonZeroToken = e(1042);
  const zeroState = topU(zeroToken);
  const nonZeroState = topU(nonZeroToken);
  const statusKeyToken = e(1155);
  const tokenKeyToken = e(1184);
  const verificationFailedToken = e(1147);
  const bindToken = "NV8XFA";
  const isMobileViewportWidthToken = "PkU0HwwBODJgEBUZGDslQi4ZChw8";

  const facts = {
    sourceFile: captchaPath,
    ct: {
      functionOffset: ct.idx,
      arrayOffset: ct.arrStart,
      length: ct.values.length,
      rotations: rotated.rotations,
    },
    OtBranch: {
      expression: "zt(s(0 === r ? e(1095, 1044) : e(1042, 972)))",
      zero: {
        eArg: 1095,
        RtArg: 390,
        otArg: 397,
        token: zeroToken,
        topUDecoded: zeroState,
      },
      nonZero: {
        eArg: 1042,
        RtArg: 337,
        otArg: 344,
        token: nonZeroToken,
        topUDecoded: nonZeroState,
      },
      payloadKeys: {
        status: {
          eArg: 1155,
          RtArg: 450,
          otArg: 457,
          token: statusKeyToken,
          topUDecoded: topU(statusKeyToken),
        },
        token: {
          eArg: 1184,
          RtArg: 479,
          otArg: 486,
          token: tokenKeyToken,
          topUDecoded: topU(tokenKeyToken),
        },
        verificationFailed: {
          eArg: 1147,
          RtArg: 442,
          otArg: 449,
          token: verificationFailedToken,
          topUDecoded: topU(verificationFailedToken),
        },
        setTimeoutMethod: {
          literal: bindToken,
          topUDecoded: topU(bindToken),
        },
        mobileViewportFlag: {
          literal: isMobileViewportWidthToken,
          topUDecoded: topU(isMobileViewportWidthToken),
        },
      },
    },
  };
  const jsonPath = path.join(outDir, "captcha_ot_branch_decode.json");
  fs.writeFileSync(jsonPath, JSON.stringify(facts, null, 2), "utf8");
  const md = [
    "# captcha Ot branch decode",
    "",
    `sourceFile=${captchaPath}`,
    `ct.functionOffset=${ct.idx}`,
    `ct.arrayOffset=${ct.arrStart}`,
    `ct.length=${ct.values.length}`,
    `ct.rotations=${rotated.rotations}`,
    "",
    "| branch | token | decoded state |",
    "|---|---|---|",
    `| 0 === r | ${zeroToken} | ${zeroState} |`,
    `| else | ${nonZeroToken} | ${nonZeroState} |`,
    "",
    "## Ot payload keys",
    "",
    "| expression | token | decoded |",
    "|---|---|---|",
    `| e(1155, 1184) | ${statusKeyToken} | ${topU(statusKeyToken)} |`,
    `| e(1184, 1252) | ${tokenKeyToken} | ${topU(tokenKeyToken)} |`,
    `| e(1147, 1081) | ${verificationFailedToken} | ${topU(verificationFailedToken)} |`,
    `| u(\"${bindToken}\") | ${bindToken} | ${topU(bindToken)} |`,
    `| u(\"${isMobileViewportWidthToken}\") | ${isMobileViewportWidthToken} | ${topU(isMobileViewportWidthToken)} |`,
    "",
    `json=${jsonPath}`,
  ].join("\n");
  const mdPath = path.join(outDir, "captcha_ot_branch_decode.md");
  fs.writeFileSync(mdPath, md, "utf8");
  process.stdout.write(md + "\n");
}

main();
