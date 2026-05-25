<template>
  <section class="step-fade-in">
    <div class="term-divider" data-tail="──────────">步骤 03: 邮箱来源</div>
    <h2 class="step-h">$&nbsp;mail source<span class="term-cursor"></span></h2>
    <p class="step-sub">选择注册邮箱来源。Cloudflare 走 catch-all；邮箱列表支持 Gmail / Outlook / 自定义邮箱账号密码或 App Password。</p>

    <div class="term-divider" data-tail="──────────" style="margin-top:20px">注册路径</div>
    <TermChoice v-model="registrationMethod" :options="registrationOptions" :cols="2" />

    <div v-if="isPhoneRegistrationMethod" class="form-stack" style="margin-top:22px">
      <TermChoice v-model="phoneForm.provider" :options="phoneProviderOptions" :cols="2" />
      <TermField v-model="phoneForm.base_url" label="手机号服务 · base_url" placeholder="https://hero-sms.com/stubs/handler_api.php" />
      <TermField v-model="phoneForm.api_key" label="Hero API Key · api_key" type="password" placeholder="YOUR_SECRET_TOKEN" />
      <TermField v-model="phoneForm.api_key_env" label="API Key 环境变量 · api_key_env" placeholder="HERO_SMS_API_KEY" />
      <TermField v-if="phoneProviderKind === 'hero_sms'" v-model="phoneForm.service" label="Hero 服务 · service" placeholder="tg" />
      <TermField v-model="phoneForm.country" :label="phoneProviderKind === 'hero_sms' ? 'Hero 国家码 · country' : '国家 · country'" :placeholder="phoneProviderKind === 'hero_sms' ? '2' : 'US'" />
      <TermField v-if="phoneProviderKind === 'hero_sms'" v-model="phoneForm.maxPrice" label="Hero 最高价格 · maxPrice" placeholder="12.5" />
      <label v-if="phoneProviderKind === 'hero_sms'" class="tf">
        <span class="tf-tag">Hero 国家码池 · countries</span>
        <textarea
          v-model="phoneForm.countries_text"
          class="tf-textarea"
          placeholder="一行一个或逗号分隔，如 151&#10;2&#10;187"
          rows="3"
        ></textarea>
      </label>
      <label v-if="phoneProviderKind === 'hero_sms'" class="tf">
        <span class="tf-tag">Hero 国家价格 · country_max_prices</span>
        <textarea
          v-model="phoneForm.country_max_prices_text"
          class="tf-textarea"
          placeholder="151=0.1&#10;2=0.2；未匹配时使用 maxPrice"
          rows="3"
        ></textarea>
      </label>
      <template v-if="phoneProviderKind !== 'hero_sms'">
        <TermField v-model="phoneForm.allocate_path" label="拿号接口 · allocate_path" placeholder="/api/phones/allocate" />
        <TermField v-model="phoneForm.otp_path" label="取码接口 · otp_path" placeholder="/api/phones/{lease_id}/otp" />
        <TermField v-model="phoneForm.otp_method" label="取码方法 · otp_method" placeholder="GET" />
      </template>
      <TermField v-model="phoneForm.otp_timeout_s" label="取码超时秒 · otp_timeout_s" />
      <TermField v-model="phoneForm.otp_poll_interval_s" label="轮询间隔秒 · otp_poll_interval_s" />
    </div>

    <div class="term-divider" data-tail="──────────" style="margin-top:24px">邮箱来源</div>
    <TermChoice v-model="mailMode" :options="mailModeOptions" :cols="2" @update:modelValue="onMailModeChange" />

    <div v-if="mailMode === 'cloudflare_kv'" class="form-stack" style="margin-top:22px">
      <TermField
        v-model="form.cf_token"
        label="API Token · cf_token"
        type="password"
        placeholder="cf api token"
      />
      <label class="tf">
        <span class="tf-tag">Zone 列表 · zone_names</span>
        <textarea
          v-model="zoneText"
          class="tf-textarea"
          placeholder="一行一个，如 example.com"
          rows="3"
        ></textarea>
      </label>
    </div>

    <div class="step-actions">
      <TermBtn v-if="mailMode === 'cloudflare_kv'" :loading="loading" @click="run">测试 token + zones</TermBtn>
    </div>

    <template v-if="mailMode === 'imap_list'">
      <div class="term-divider" data-tail="──────────" style="margin-top:24px">IMAP 邮箱列表</div>
      <div class="form-stack">
        <TermField v-model="mailForm.otp_timeout" label="OTP 超时 · otp_timeout" />
        <label class="tf">
          <span class="tf-tag">邮箱列表</span>
          <textarea
            v-model="accountsText"
            class="tf-textarea tf-textarea--mail"
            placeholder="email----mail_password，一行一个；也兼容 email_password"
            rows="5"
          ></textarea>
        </label>
      </div>
      <div class="step-actions">
        <TermBtn :loading="savingMail" @click="saveMailAccounts">保存邮箱列表</TermBtn>
        <TermBtn :loading="listingMail" @click="listMail">登录邮箱 + 拉最近邮件</TermBtn>
      </div>

      <div v-if="mailStatus" class="result-block result--ok" style="margin-top:14px">
        <div class="result-head"><span class="result-icon">✓</span> {{ mailStatus.count }} 个邮箱 · {{ mailStatus.path }}{{ saveDeltaText }}</div>
        <ul class="result-list">
          <li v-for="a in mailStatus.accounts" :key="a.email" class="row-ok">
            <span class="row-name">{{ a.email }}</span>
            <span class="row-msg">{{ a.provider }} · {{ a.status }}</span>
          </li>
        </ul>
      </div>

      <div v-if="mailList" class="result-block result--ok" style="margin-top:14px">
        <div class="result-head"><span class="result-icon">✓</span> {{ mailList.email }} 最近邮件 {{ mailList.count }} 封</div>
        <ul class="result-list">
          <li v-for="m in mailList.messages" :key="m.uid" class="row-ok mail-row">
            <span class="row-name">{{ shortDate(m.date) }}</span>
            <span class="row-msg">
              <strong>{{ m.subject || '(no subject)' }}</strong>
              <small>{{ m.from }}</small>
              <em>{{ m.snippet }}</em>
            </span>
          </li>
        </ul>
      </div>

      <div v-if="mailError" class="result-block result--fail" style="margin-top:14px">
        <div class="result-head"><span class="result-icon">✗</span> {{ mailError }}</div>
      </div>
    </template>

    <div v-if="result && mailMode === 'cloudflare_kv'" class="result-block" :class="`result--${result.status}`">
      <div class="result-head">
        <span class="result-icon">{{ icon(result.status) }}</span>
        <span>{{ result.message }}</span>
      </div>
      <ul v-if="result.checks?.length" class="result-list">
        <li v-for="c in result.checks" :key="c.name" :class="`row-${c.status}`">
          <span class="row-name">{{ c.name }}</span>
          <span class="row-msg">{{ c.message }}</span>
        </li>
      </ul>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from "vue";
import { useWizardStore } from "../../stores/wizard";
import type { PreflightResult } from "../../api/client";
import { api } from "../../api/client";
import TermField from "../term/TermField.vue";
import TermBtn from "../term/TermBtn.vue";
import TermChoice from "../term/TermChoice.vue";

const store = useWizardStore();
const registrationInit = store.answers.registration ?? {};
const phoneInit = store.answers.phone ?? {};
const registrationMethod = ref(registrationInit.method ?? "browser");
function listText(value: unknown) {
  if (Array.isArray(value)) return value.map((v) => String(v).trim()).filter(Boolean).join("\n");
  return String(value ?? "");
}
function priceMapText(value: unknown) {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return Object.entries(value as Record<string, unknown>)
      .map(([k, v]) => `${k}=${String(v ?? "")}`)
      .join("\n");
  }
  return String(value ?? "");
}
function parseListText(value: string) {
  return String(value || "")
    .split(/[\s,，;；]+/)
    .map((v) => v.trim())
    .filter(Boolean);
}
function parsePriceMapText(value: string) {
  const out: Record<string, string> = {};
  String(value || "")
    .split(/[\n,，;；]+/)
    .map((v) => v.trim())
    .filter(Boolean)
    .forEach((item) => {
      const parts = item.includes("=") ? item.split("=") : item.split(":");
      if (parts.length < 2) return;
      const key = parts[0].trim();
      const val = parts.slice(1).join(":").trim();
      if (key && val) out[key] = val;
    });
  return out;
}
const phoneForm = ref({
  enabled: phoneInit.enabled ?? false,
  provider: phoneInit.provider ?? "hero_sms",
  base_url: phoneInit.base_url ?? "https://hero-sms.com/stubs/handler_api.php",
  api_key: phoneInit.api_key ?? "",
  api_key_env: phoneInit.api_key_env ?? "HERO_SMS_API_KEY",
  country: phoneInit.country ?? "2",
  countries_text: listText(phoneInit.countries),
  service: phoneInit.service ?? "tg",
  maxPrice: String(phoneInit.maxPrice ?? phoneInit.max_price ?? ""),
  country_max_prices_text: priceMapText(phoneInit.country_max_prices),
  lease_ttl_s: String(phoneInit.lease_ttl_s ?? 300),
  request_timeout_s: String(phoneInit.request_timeout_s ?? 20),
  allocate_path: phoneInit.allocate_path ?? "/api/phones/allocate",
  otp_path: phoneInit.otp_path ?? "/api/phones/{lease_id}/otp",
  otp_method: phoneInit.otp_method ?? "GET",
  otp_timeout_s: String(phoneInit.otp_timeout_s ?? 180),
  otp_poll_interval_s: String(phoneInit.otp_poll_interval_s ?? 3),
  release_path: phoneInit.release_path ?? "/api/phones/{lease_id}/release",
  fail_path: phoneInit.fail_path ?? "/api/phones/{lease_id}/fail",
  verified_path: phoneInit.verified_path ?? "/api/phones/{lease_id}/verified",
});
const mailInit = store.answers.mail ?? {};
const mailMode = ref(mailInit.mode ?? "cloudflare_kv");
const init = store.answers.cloudflare ?? {};
const form = ref({
  cf_token: init.cf_token ?? "",
  zone_names: (init.zone_names ?? []) as string[],
});
const mailForm = ref({
  otp_timeout: String(mailInit.otp_timeout ?? 180),
  mark_seen: Boolean(mailInit.mark_seen ?? false),
});
const accountsText = ref("");
const savingMail = ref(false);
const listingMail = ref(false);
const mailStatus = ref<any>(null);
const mailList = ref<any>(null);
const mailError = ref("");
const saveDeltaText = computed(() => {
  if (!mailStatus.value || mailStatus.value.inserted_count === undefined) return "";
  return ` · 本次新增 ${mailStatus.value.inserted_count} / 跳过 ${mailStatus.value.skipped_existing ?? 0}`;
});

const mailModeOptions = [
  { value: "cloudflare_kv", label: "Cloudflare KV", desc: "catch-all 域名 + Worker/KV 自动取码" },
  { value: "imap_list", label: "IMAP 列表", desc: "Gmail / Outlook / 自定义邮箱账号密码" },
];
const registrationOptions = [
  { value: "browser", label: "邮箱浏览器", desc: "Camoufox 走邮箱注册" },
  { value: "protocol", label: "邮箱协议", desc: "auth_flow HTTP 链路" },
  { value: "phone_browser", label: "手机号浏览器", desc: "Phone 入口 + provider 拿号/取码" },
  { value: "phone_protocol", label: "手机号协议", desc: "手机号纯协议 + provider 拿号/取码" },
];
const phoneProviderOptions = [
  { value: "hero_sms", label: "Hero SMS", desc: "getNumberV2 + getStatusV2" },
  { value: "http", label: "HTTP JSON", desc: "自建 allocate / otp 接口" },
];
const phoneProviderKind = computed(() => (phoneForm.value.provider || "hero_sms").replace("-", "_"));
const isPhoneRegistrationMethod = computed(() =>
  registrationMethod.value === "phone_browser" || registrationMethod.value === "phone_protocol"
);
const zoneText = computed({
  get: () => form.value.zone_names.join("\n"),
  set: (v: string) => (form.value.zone_names = v.split("\n").map((s) => s.trim()).filter(Boolean)),
});
const loading = ref(false);
const result = ref<PreflightResult | null>(store.preflight.cloudflare ?? null);

async function run() {
  store.setAnswer("cloudflare", form.value);
  persistMailAnswer();
  await store.saveToServer();
  loading.value = true;
  try {
    result.value = await store.runPreflight("cloudflare", {
      cf_token: form.value.cf_token,
      zone_names: form.value.zone_names,
    });
  } finally { loading.value = false; }
}

watch(form, () => store.setAnswer("cloudflare", form.value), { deep: true });
watch(mailForm, () => persistMailAnswer(), { deep: true });
watch([registrationMethod, phoneForm], () => persistRegistrationAnswer(), { deep: true });

function onMailModeChange(v: string) {
  mailMode.value = v;
  persistMailAnswer();
  store.saveToServer();
}

function persistMailAnswer() {
  store.setAnswer("mail", {
    mode: mailMode.value,
    otp_timeout: Number(mailForm.value.otp_timeout || 180),
    mark_seen: mailForm.value.mark_seen,
  });
}

function persistRegistrationAnswer() {
  store.setAnswer("registration", { method: registrationMethod.value });
  store.setAnswer("phone", {
    enabled: isPhoneRegistrationMethod.value,
    provider: phoneForm.value.provider || "hero_sms",
    base_url: phoneForm.value.base_url,
    api_key: phoneForm.value.api_key,
    api_key_env: phoneForm.value.api_key_env || (phoneProviderKind.value === "hero_sms" ? "HERO_SMS_API_KEY" : "PHONE_PROVIDER_API_KEY"),
    country: phoneForm.value.country || (phoneProviderKind.value === "hero_sms" ? "2" : "US"),
    countries: parseListText(phoneForm.value.countries_text),
    service: phoneForm.value.service || "tg",
    maxPrice: phoneForm.value.maxPrice,
    country_max_prices: parsePriceMapText(phoneForm.value.country_max_prices_text),
    lease_ttl_s: Number(phoneForm.value.lease_ttl_s || 300),
    request_timeout_s: Number(phoneForm.value.request_timeout_s || 20),
    allocate_path: phoneForm.value.allocate_path || "/api/phones/allocate",
    otp_path: phoneForm.value.otp_path || "/api/phones/{lease_id}/otp",
    otp_method: (phoneForm.value.otp_method || "GET").toUpperCase(),
    otp_timeout_s: Number(phoneForm.value.otp_timeout_s || 180),
    otp_poll_interval_s: Number(phoneForm.value.otp_poll_interval_s || 3),
    release_path: phoneForm.value.release_path || "/api/phones/{lease_id}/release",
    fail_path: phoneForm.value.fail_path || "/api/phones/{lease_id}/fail",
    verified_path: phoneForm.value.verified_path || "/api/phones/{lease_id}/verified",
  });
}

async function saveMailAccounts() {
  mailError.value = "";
  mailList.value = null;
  savingMail.value = true;
  try {
    const r = await api.post("/mail/accounts/save", {
      accounts_text: accountsText.value,
    });
    mailStatus.value = r.data;
    persistMailAnswer();
    await store.saveToServer();
    const result: PreflightResult = {
      status: "ok",
      message: `邮箱列表已保存: 总数 ${r.data.count}，本次新增 ${r.data.inserted_count ?? r.data.count}，跳过 ${r.data.skipped_existing ?? 0}`,
      checks: [],
    };
    store.setPreflight("imap_mail", result);
  } catch (e: any) {
    mailError.value = e?.response?.data?.detail || String(e);
  } finally {
    savingMail.value = false;
  }
}

async function listMail() {
  mailError.value = "";
  mailList.value = null;
  listingMail.value = true;
  try {
    const r = await api.post("/mail/accounts/list", {
      accounts_text: accountsText.value,
      limit: 10,
    });
    mailList.value = r.data;
    const result: PreflightResult = {
      status: "ok",
      message: `${r.data.email} 邮件列表 ${r.data.count} 封`,
      checks: [],
    };
    store.setPreflight("imap_mail", result);
  } catch (e: any) {
    mailError.value = e?.response?.data?.detail || String(e);
    store.setPreflight("imap_mail", { status: "fail", message: mailError.value, checks: [] });
  } finally {
    listingMail.value = false;
  }
}

async function loadMailStatus() {
  if (mailMode.value !== "imap_list") return;
  try {
    const r = await api.get("/mail/accounts/status");
    if (r.data.count) {
      mailStatus.value = r.data;
      persistMailAnswer();
    }
  } catch {}
}

function shortDate(v: string) {
  if (!v) return "";
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return v.slice(0, 16);
  return `${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

onMounted(() => {
  persistRegistrationAnswer();
  persistMailAnswer();
  loadMailStatus();
});

function icon(s: string) {
  return s === "ok" ? "✓" : s === "fail" ? "✗" : s === "warn" ? "▲" : "○";
}
</script>

<style scoped>
/* Local overrides only – shared styles come from theme.css */
.tf { display: grid; grid-template-columns: minmax(140px, max-content) minmax(0, 1fr); border: 1px solid var(--border); background: var(--bg-base); transition: border-color 80ms; }
.tf:focus-within { border-color: var(--accent); }
.tf-tag { background: var(--bg-panel); color: var(--fg-tertiary); padding: 10px 12px; font-size: 11px; font-weight: 700; letter-spacing: 0.04em; border-right: 1px solid var(--border); display: flex; align-items: flex-start; white-space: nowrap; }
.tf-textarea { background: transparent; border: 0; padding: 10px 12px; color: var(--fg-primary); font: inherit; font-size: 13px; outline: none; resize: vertical; min-height: 60px; width: 100%; }
.tf-textarea::placeholder { color: var(--fg-tertiary); opacity: 0.6; }
.tf-textarea--mail { min-height: 120px; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; }
.mail-row .row-msg { display: grid; gap: 3px; white-space: normal; }
.mail-row small { color: var(--fg-tertiary); font-style: normal; overflow: hidden; text-overflow: ellipsis; }
.mail-row em { color: var(--fg-secondary); font-style: normal; overflow: hidden; text-overflow: ellipsis; }
</style>
