import crypto from "crypto";

const JSON_ESCAPE_RE = /[\\\"\u0000-\u001f\u007f-\u009f\u00ad\u0600-\u0604\u070f\u17b4\u17b5\u200c-\u200f\u2028-\u202f\u2060-\u206f\ufeff\ufff0-\uffff]/g;
const JSON_ESCAPES = {
  "\b": "\\b",
  "\t": "\\t",
  "\n": "\\n",
  "\f": "\\f",
  "\r": "\\r",
  "\v": "\\v",
  '"': '\\"',
  "\\": "\\\\",
};

export function sha16(value) {
  const s = typeof value === "string" ? value : JSON.stringify(value ?? "");
  return crypto.createHash("sha256").update(s).digest("hex").slice(0, 16);
}

export function xorString(input, key) {
  let out = "";
  for (let i = 0; i < input.length; i += 1) {
    out += String.fromCharCode(input.charCodeAt(i) ^ key);
  }
  return out;
}

export function jsBtoa(value) {
  return Buffer.from(String(value), "utf8").toString("base64");
}

export function jsAtob(value) {
  return Buffer.from(String(value), "base64").toString("binary");
}

export function jsAtobUtf8(value) {
  return Buffer.from(String(value), "base64").toString("utf8");
}

export function hsUt(value) {
  const kind = typeof value;
  if (kind === "undefined") return '"undefined"';
  if (kind === "boolean") return String(value);
  if (kind === "number") {
    const s = String(value);
    return s === "NaN" || s === "Infinity" || s === "-Infinity" ? "null" : s;
  }
  if (kind === "string") return quoteString(value);
  if (value === null || value instanceof RegExp) return "null";
  if (value instanceof Date) {
    return [
      '"',
      value.getFullYear(),
      "-",
      value.getMonth() + 1,
      "-",
      value.getDate(),
      "T",
      value.getHours(),
      ":",
      value.getMinutes(),
      ":",
      value.getSeconds(),
      ".",
      value.getMilliseconds(),
      '"',
    ].join("");
  }
  if (Array.isArray(value)) {
    const parts = ["["];
    for (const item of value) {
      parts.push(hsUt(item) || '"undefined"', ",");
    }
    parts[parts.length > 1 ? parts.length - 1 : parts.length] = "]";
    return parts.join("");
  }
  const parts = ["{"];
  for (const key of Object.keys(value)) {
    if (typeof value[key] !== "undefined") {
      parts.push(quoteString(key), ":", hsUt(value[key]) || '"undefined"', ",");
    }
  }
  parts[parts.length > 1 ? parts.length - 1 : parts.length] = "}";
  return parts.join("");
}

function quoteString(value) {
  JSON_ESCAPE_RE.lastIndex = 0;
  return `"${JSON_ESCAPE_RE.test(value) ? value.replace(JSON_ESCAPE_RE, escapeJsonChar) : value}"`;
}

function escapeJsonChar(char) {
  return JSON_ESCAPES[char] || `\\u${(`0000${char.charCodeAt(0).toString(16)}`).slice(-4)}`;
}

export function payloadBaseFromActivities(activities) {
  const cloned = Array.isArray(activities) ? activities.slice() : [];
  return jsBtoa(xorString(hsUt(cloned), 50));
}

export function payloadSaltFromQi(qi) {
  return xorString(jsBtoa(qi || "1604064986000"), 10);
}

export function qiFromPayloadSalt(salt) {
  const encoded = xorString(salt, 10);
  return Buffer.from(encoded, "base64").toString("utf8");
}

export function payloadSlots(saltLen, baseLen, cu) {
  const h = xorString(jsBtoa(cu), 10);
  const slots = [];
  let maxScore = -1;
  for (let p = 0; p < saltLen; p += 1) {
    const multiplier = Math.floor(p / h.length + 1);
    const index = p >= h.length ? p % h.length : p;
    const score = h.charCodeAt(index) * h.charCodeAt(multiplier);
    if (score > maxScore) maxScore = score;
  }
  for (let b = 0; b < saltLen; b += 1) {
    const multiplier = Math.floor(b / h.length) + 1;
    const index = b % h.length;
    let score = h.charCodeAt(index) * h.charCodeAt(multiplier);
    if (score >= baseLen) {
      score = Math.floor((score / maxScore) * (baseLen - 1));
    }
    while (slots.includes(score)) score += 1;
    slots.push(score);
  }
  return slots.sort((left, right) => left - right);
}

export function encodePayload(activities, meta, qi) {
  const base = payloadBaseFromActivities(activities);
  const salt = payloadSaltFromQi(qi);
  const slots = payloadSlots(salt.length, base.length, meta?.cu || "");
  let out = "";
  let cursor = 0;
  const saltChars = salt.split("");
  for (let i = 0; i < salt.length; i += 1) {
    const end = slots[i] - i - 1;
    out += base.substring(cursor, end) + saltChars[i];
    cursor = end;
  }
  out += base.substring(cursor);
  return { payload: out, base, salt, slots };
}

export function decodePayload(payload, activities, meta) {
  const base = payloadBaseFromActivities(activities);
  const saltLen = String(payload || "").length - base.length;
  if (saltLen < 0) {
    return { ok: false, reason: "payload shorter than computed base", baseLen: base.length, payloadLen: String(payload || "").length };
  }
  const slots = payloadSlots(saltLen, base.length, meta?.cu || "");
  let rebuiltBase = "";
  let salt = "";
  let cursor = 0;
  for (let i = 0; i < saltLen; i += 1) {
    const end = slots[i] - i - 1;
    const segmentLen = end - cursor;
    rebuiltBase += payload.slice(cursor + i, cursor + i + segmentLen);
    salt += payload[cursor + i + segmentLen] || "";
    cursor = end;
  }
  rebuiltBase += payload.slice(cursor + saltLen);
  const qi = salt ? qiFromPayloadSalt(salt) : "";
  return {
    ok: rebuiltBase === base,
    payloadLen: String(payload || "").length,
    baseLen: base.length,
    saltLen,
    baseSha16: sha16(base),
    payloadSha16: sha16(payload || ""),
    saltSha16: sha16(salt),
    qi,
    qiSha16: qi ? sha16(qi) : "",
    slots,
  };
}

export function decodePayloadRaw(payload, meta) {
  const rawPayload = String(payload || "");
  const cu = meta?.cu || meta?.uuid || "";
  for (let saltLen = 0; saltLen <= Math.min(200, rawPayload.length); saltLen += 1) {
    try {
      const baseLen = rawPayload.length - saltLen;
      const slots = payloadSlots(saltLen, baseLen, cu);
      let rebuiltBase = "";
      let salt = "";
      let cursor = 0;
      for (let i = 0; i < saltLen; i += 1) {
        const end = slots[i] - i - 1;
        const segmentLen = end - cursor;
        if (segmentLen < 0) throw new Error("negative segment");
        rebuiltBase += rawPayload.slice(cursor + i, cursor + i + segmentLen);
        salt += rawPayload[cursor + i + segmentLen] || "";
        cursor = end;
      }
      rebuiltBase += rawPayload.slice(cursor + saltLen);
      const serialized = xorString(jsAtobUtf8(rebuiltBase), 50);
      if (!serialized.startsWith("[{\"t\"")) continue;
      const activities = JSON.parse(serialized);
      const qi = salt ? qiFromPayloadSalt(salt) : "";
      const canonical = hsUt(activities);
      return {
        ok: canonical === serialized,
        payloadLen: rawPayload.length,
        payloadSha16: sha16(rawPayload),
        saltLen,
        qi,
        qiSha16: qi ? sha16(qi) : "",
        baseLen: rebuiltBase.length,
        baseSha16: sha16(rebuiltBase),
        serialized,
        serializedSha16: sha16(serialized),
        activities,
        canonicalSha16: sha16(canonical),
      };
    } catch {
      // Continue scanning possible salt lengths.
    }
  }
  return {
    ok: false,
    payloadLen: rawPayload.length,
    payloadSha16: sha16(rawPayload),
    reason: "no valid raw payload decode",
  };
}

export function computePc(serialized, cu, tag, ft) {
  const seed = [cu, tag, ft].join(":");
  const hmac = crypto.createHmac("md5", seed).update(serialized).digest("hex");
  let digits = "";
  let rest = "";
  for (const char of hmac) {
    const code = char.charCodeAt(0);
    if (code >= 48 && code <= 57) digits += char;
    else rest += String(code % 10);
  }
  const mixed = digits + rest;
  let out = "";
  for (let i = 0; i < mixed.length; i += 2) out += mixed[i];
  return out;
}
