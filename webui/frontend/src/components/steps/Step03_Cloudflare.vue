<template>
  <section class="step-fade-in">
    <div class="term-divider" data-tail="──────────">步骤 03: 邮箱来源</div>
    <h2 class="step-h">$&nbsp;mail source<span class="term-cursor"></span></h2>
    <p class="step-sub">选择注册邮箱来源。Cloudflare 走 catch-all；邮箱列表支持 Gmail / Outlook / 自定义邮箱账号密码或 App Password。</p>

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
        <TermField v-model="mailForm.accounts_path" label="列表路径 · accounts_path" placeholder="output/email_accounts.csv" />
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
        <div class="result-head"><span class="result-icon">✓</span> {{ mailStatus.count }} 个邮箱 · {{ mailStatus.path }}</div>
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
const mailInit = store.answers.mail ?? {};
const mailMode = ref(mailInit.mode ?? "cloudflare_kv");
const init = store.answers.cloudflare ?? {};
const form = ref({
  cf_token: init.cf_token ?? "",
  zone_names: (init.zone_names ?? []) as string[],
});
const mailForm = ref({
  accounts_path: mailInit.accounts_path ?? "output/email_accounts.csv",
  otp_timeout: String(mailInit.otp_timeout ?? 180),
  mark_seen: Boolean(mailInit.mark_seen ?? false),
});
const accountsText = ref("");
const savingMail = ref(false);
const listingMail = ref(false);
const mailStatus = ref<any>(null);
const mailList = ref<any>(null);
const mailError = ref("");

const mailModeOptions = [
  { value: "cloudflare_kv", label: "Cloudflare KV", desc: "catch-all 域名 + Worker/KV 自动取码" },
  { value: "imap_list", label: "IMAP 列表", desc: "Gmail / Outlook / 自定义邮箱账号密码" },
];
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

function onMailModeChange(v: string) {
  mailMode.value = v;
  persistMailAnswer();
  store.saveToServer();
}

function persistMailAnswer() {
  store.setAnswer("mail", {
    mode: mailMode.value,
    accounts_path: mailForm.value.accounts_path || "output/email_accounts.csv",
    otp_timeout: Number(mailForm.value.otp_timeout || 180),
    mark_seen: mailForm.value.mark_seen,
  });
}

async function saveMailAccounts() {
  mailError.value = "";
  mailList.value = null;
  savingMail.value = true;
  try {
    const r = await api.post("/mail/accounts/save", {
      accounts_text: accountsText.value,
      path: mailForm.value.accounts_path,
    });
    mailStatus.value = r.data;
    mailForm.value.accounts_path = r.data.path;
    persistMailAnswer();
    await store.saveToServer();
    const result: PreflightResult = {
      status: "ok",
      message: `邮箱列表已保存: ${r.data.count} 个`,
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
      path: mailForm.value.accounts_path,
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
    const r = await api.get("/mail/accounts/status", { params: { path: mailForm.value.accounts_path } });
    if (r.data.count) {
      mailStatus.value = r.data;
      mailForm.value.accounts_path = r.data.path;
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
