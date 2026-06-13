import crypto from "crypto";

const DEFAULT_SEPARATOR = "~~~~";

export function sha16(value) {
  const s = typeof value === "string" ? value : JSON.stringify(value ?? "");
  if (!s) return "";
  return crypto.createHash("sha256").update(s).digest("hex").slice(0, 16);
}

export function xorString(input, key) {
  const n = Number(key);
  if (!Number.isInteger(n) || n < 0 || n > 255) {
    throw new Error(`invalid xor key: ${key}`);
  }
  let out = "";
  for (let i = 0; i < input.length; i += 1) {
    out += String.fromCharCode(input.charCodeAt(i) ^ n);
  }
  return out;
}

export function decodeOb(ob, xorKey, separator = DEFAULT_SEPARATOR) {
  const decodedBase64 = Buffer.from(String(ob || ""), "base64").toString("binary");
  const decoded = xorString(decodedBase64, xorKey);
  return {
    obLen: String(ob || "").length,
    obSha16: sha16(ob || ""),
    xorKey: Number(xorKey),
    decoded,
    decodedSha16: sha16(decoded),
    parts: decoded ? decoded.split(separator).filter(Boolean) : [],
  };
}

export function encodeOb(partsOrDecoded, xorKey, separator = DEFAULT_SEPARATOR) {
  const decoded = Array.isArray(partsOrDecoded)
    ? partsOrDecoded.join(separator)
    : String(partsOrDecoded || "");
  const xored = xorString(decoded, xorKey);
  return {
    ob: Buffer.from(xored, "binary").toString("base64").replace(/=+$/g, ""),
    xorKey: Number(xorKey),
    decoded,
    decodedSha16: sha16(decoded),
  };
}

export function parseDecodedPart(part) {
  const fields = String(part || "").split("|");
  const key = fields[0] || "";
  const args = fields.slice(1);
  const out = { key, args, raw: String(part || "") };
  if (key === "IoIoIo" && args[0] === "score") {
    out.kind = "score";
    out.score = args[1] || "";
    out.scoreType = args[2] || "";
  } else if (key === "IoooII" && args[0] === "_px3") {
    out.kind = "px3";
    out.name = args[0];
    out.ttl = args[1] || "";
    out.token = tokenShape(args[2] || "");
    out.domainFlag = args[3] || "";
    out.cookieTtl = args[4] || "";
  } else if (key === "oIIoIIoo" && args[0] === "_pxde") {
    out.kind = "pxde";
    out.name = args[0];
    out.ttl = args[1] || "";
    out.token = tokenShape(args[2] || "");
    out.domainFlag = args[3] || "";
    out.cookieTtl = args[4] || "";
  } else if (key === "IooIoo") {
    out.kind = "pxvid";
    out.value = args[0] || "";
    out.ttl = args[1] || "";
    out.domainFlag = args[2] || "";
  } else if (key === "IoIIIo") {
    out.kind = "cu";
    out.value = args[0] || "";
  } else if (key === "IoIIII") {
    out.kind = "cs";
    out.value = args[0] || "";
    out.token = tokenShape(args[0] || "");
  } else if (key === "oIIoIooo") {
    out.kind = "captcha_result_callback";
    out.result = args[0] || "";
  } else if (key === "IIooII") {
    out.kind = "cookie_directive";
    out.name = args[0] || "";
    out.ttl = args[1] || "";
    out.valueShape = tokenShape(args[2] || "");
  }
  return out;
}

export function tokenShape(value) {
  const s = String(value || "");
  return {
    present: Boolean(s),
    len: s.length,
    parts: s ? s.split(":").length : 0,
    sha16: s ? sha16(s) : "",
  };
}

export function runDecodedStateMachine(parts) {
  const events = [];
  const state = {
    scores: [],
    cookies: {},
    cuSeen: false,
    captchaResult: null,
    terminal: "observed",
  };

  for (const raw of parts || []) {
    const part = parseDecodedPart(raw);
    events.push({ type: "dispatch", key: part.key, kind: part.kind || "unknown", args: part.args });

    if (part.kind === "score") {
      state.scores.push({ score: part.score, type: part.scoreType });
      events.push({ type: "score", score: part.score, scoreType: part.scoreType });
    }
    if (part.kind === "px3" || part.kind === "pxde" || part.kind === "pxvid" || part.kind === "cookie_directive") {
      const name = part.name || part.key;
      state.cookies[name] = part.token || part.valueShape || tokenShape(part.value || "");
      events.push({ type: "cookie", name, shape: state.cookies[name] });
    }
    if (part.kind === "cu") {
      state.cuSeen = true;
      events.push({ type: "cu", value: part.value });
    }
    if (part.kind === "cs") {
      state.cs = part.token;
      events.push({ type: "cs", shape: part.token });
    }
    if (part.kind === "captcha_result_callback") {
      state.captchaResult = part.result;
      const otState = part.result === "0" ? "succeeded" : "failed";
      state.terminal = otState;
      events.push({
        type: "captcha_result_callback",
        result: part.result,
        syntheticCall: `oIIoIooo(${JSON.stringify(part.result)}) -> Wc -> Ot(${Number(part.result)})`,
        otState,
      });
    }
  }

  return { state, events };
}
