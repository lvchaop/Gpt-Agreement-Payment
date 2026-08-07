<script setup lang="ts">
import { ref, watch } from "vue";
import { useRouter } from "vue-router";

import PageHeader from "../components/PageHeader.vue";
import { resourcesApi } from "../api/resources";
import { useOpsStore } from "../stores/ops";

const store = useOpsStore();
const router = useRouter();

const mode = ref("email_protocol_no_phone");
const count = ref(1);
const workCount = ref(1);
const proxyCountry = ref("US");
const authorizeCodexAfterSecurity = ref(false);
const mailProvider = ref("outlook");
const emailDomain = ref("");
const projectKey = ref("openai-register");
const callerId = ref("refactor-app-protocol-registration");
const browserHeadless = ref(true);
const browserOtpTimeoutS = ref(180);

const phoneBaseUrl = ref("https://hero-sms.com/stubs/handler_api.php");
const phoneApiKeyEnv = ref("HERO_SMS_API_KEY");
const phoneService = ref("dr");
const phoneCountry = ref("");
const phoneCountries = ref("151,73,16");
const phoneMaxPrice = ref("0.05");
const phoneCountryMaxPrices = ref("");
const phoneMaxNumberAttempts = ref(3);
const phoneOtpTimeoutS = ref(180);
const phoneOtpPollIntervalS = ref(3);
const submitting = ref(false);

watch(mailProvider, (provider) => {
  if (provider === "icloud_hide_my_email") {
    emailDomain.value = "";
  } else {
    authorizeCodexAfterSecurity.value = false;
  }
});

function parseCountries(value: string): string[] {
  return value
    .split(/[\s,，;；]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function parseCountryMaxPrices(value: string): Record<string, string> {
  const prices: Record<string, string> = {};
  value
    .split(/[\n,，;；]+/)
    .map((item) => item.trim())
    .filter(Boolean)
    .forEach((item) => {
      const separator = item.includes("=") ? "=" : ":";
      const [country, price] = item.split(separator, 2).map((part) => part.trim());
      if (country && price) prices[country] = price;
    });
  return prices;
}

async function submitJob() {
  const normalizedProxyCountry = proxyCountry.value.trim().toUpperCase();
  if (!/^[A-Z]{2}$/.test(normalizedProxyCountry)) {
    store.toast("国家代码格式错误", "请输入两位国家代码，例如 US 或 JP", "error");
    return;
  }
  proxyCountry.value = normalizedProxyCountry;
  submitting.value = true;
  try {
    const result = await resourcesApi.createProtocolRegistrationJob({
      mode: mode.value,
      count: count.value,
      work_count: workCount.value,
      proxy_country: normalizedProxyCountry,
      authorize_codex_after_security: authorizeCodexAfterSecurity.value,
      mail_provider: mailProvider.value,
      email_domain: emailDomain.value,
      project_key: projectKey.value,
      caller_id: callerId.value,
      browser_headless: browserHeadless.value,
      browser_otp_timeout_s: browserOtpTimeoutS.value,
      phone_provider: "hero_sms",
      phone_base_url: phoneBaseUrl.value,
      phone_api_key_env: phoneApiKeyEnv.value,
      phone_service: phoneService.value,
      phone_country: phoneCountry.value,
      phone_countries: parseCountries(phoneCountries.value),
      phone_max_price: phoneMaxPrice.value,
      phone_country_max_prices: parseCountryMaxPrices(phoneCountryMaxPrices.value),
      phone_max_number_attempts: phoneMaxNumberAttempts.value,
      phone_otp_timeout_s: phoneOtpTimeoutS.value,
      phone_otp_poll_interval_s: phoneOtpPollIntervalS.value,
      created_by: "ops-ui",
    });
    store.toast("注册任务已创建", `job=${result.job_id}`, "success");
    await router.push({ name: "job-trace", params: { jobId: result.job_id } });
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <div>
    <PageHeader
      title="账号注册"
      description="邮箱支持浏览器或纯协议注册；手机号纯协议注册完成后绑定邮箱。"
    />

    <section class="panel registration-panel">
      <div class="grid">
        <label>
          <span>模式</span>
          <select v-model="mode" class="input">
            <option value="email_protocol_no_phone">邮箱纯协议注册，不绑手机号</option>
            <option value="email_browser_no_phone">邮箱浏览器注册，不绑手机号</option>
            <option value="phone_protocol_bind_email">手机号纯协议注册，绑定邮箱</option>
          </select>
        </label>
        <label>
          <span>总数量 count</span>
          <input v-model.number="count" class="input" min="1" type="number" />
        </label>
        <label>
          <span>同时 Work 数</span>
          <input v-model.number="workCount" class="input" min="1" max="500" type="number" />
        </label>
        <label>
          <span>注册代理国家</span>
          <input
            v-model="proxyCountry"
            autocapitalize="characters"
            class="input country-input"
            maxlength="2"
            pattern="[A-Za-z]{2}"
            placeholder="US"
            required
            @input="proxyCountry = proxyCountry.toUpperCase()"
          />
        </label>
        <label>
          <span>邮箱 provider</span>
          <select v-model="mailProvider" class="input">
            <option value="outlook">outlook（outlook/hotmail/live）</option>
            <option value="imap">imap</option>
            <option value="custom">custom</option>
            <option value="cloudflare_temp_mail">cloudflare_temp_mail</option>
            <option value="icloud_hide_my_email">iCloud 隐藏邮箱</option>
          </select>
        </label>
        <label v-if="mailProvider === 'icloud_hide_my_email'" class="checkbox-field">
          <span>注册后 Codex 授权</span>
          <input v-model="authorizeCodexAfterSecurity" type="checkbox" />
        </label>
        <label>
          <span>邮箱域名</span>
          <input
            v-model="emailDomain"
            class="input"
            :disabled="mailProvider === 'icloud_hide_my_email'"
            :placeholder="mailProvider === 'icloud_hide_my_email' ? 'iCloud 模式无需填写' : '可空'"
          />
        </label>
        <label>
          <span>project_key</span>
          <input v-model="projectKey" class="input" />
        </label>
        <label>
          <span>caller_id</span>
          <input v-model="callerId" class="input" />
        </label>
      </div>
    </section>

    <section v-if="mode === 'email_browser_no_phone'" class="panel registration-panel">
      <h2>浏览器配置</h2>
      <div class="grid">
        <label>
          <span>Headless</span>
          <input v-model="browserHeadless" type="checkbox" />
        </label>
        <label>
          <span>邮箱 OTP timeout 秒</span>
          <input v-model.number="browserOtpTimeoutS" class="input" min="1" type="number" />
        </label>
      </div>
    </section>

    <section v-if="mode === 'phone_protocol_bind_email'" class="panel registration-panel">
      <h2>Hero SMS 配置</h2>
      <div class="grid">
        <label>
          <span>base_url</span>
          <input v-model="phoneBaseUrl" class="input" />
        </label>
        <label>
          <span>API Key 环境变量</span>
          <input v-model="phoneApiKeyEnv" class="input" />
        </label>
        <label>
          <span>service</span>
          <input v-model="phoneService" class="input" />
        </label>
        <label>
          <span>country（countries 为空时使用）</span>
          <input v-model="phoneCountry" class="input" />
        </label>
        <label>
          <span>countries（优先）</span>
          <input v-model="phoneCountries" class="input" placeholder="逗号或空格分隔，可空" />
        </label>
        <label>
          <span>maxPrice</span>
          <input v-model="phoneMaxPrice" class="input" placeholder="默认 0.05" />
        </label>
        <label>
          <span>各国家 maxPrice</span>
          <input
            v-model="phoneCountryMaxPrices"
            class="input"
            placeholder="例如 2=12.5, 73=10"
          />
        </label>
        <label>
          <span>max_number_attempts</span>
          <input v-model.number="phoneMaxNumberAttempts" class="input" min="1" type="number" />
        </label>
        <label>
          <span>OTP timeout 秒</span>
          <input v-model.number="phoneOtpTimeoutS" class="input" min="1" type="number" />
        </label>
        <label>
          <span>OTP poll 间隔秒</span>
          <input v-model.number="phoneOtpPollIntervalS" class="input" min="1" type="number" />
        </label>
      </div>
    </section>

    <div class="actions">
      <button class="btn primary" :disabled="submitting" @click="submitJob">
        {{ submitting ? "创建中..." : "创建注册任务" }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.registration-panel {
  margin-bottom: 14px;
  padding: 16px;
}

.registration-panel h2 {
  font-size: 15px;
  margin: 0 0 14px;
}

.grid {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
}

label {
  display: grid;
  gap: 6px;
}

label span {
  color: var(--text-muted);
  font-size: 12px;
  font-weight: 800;
}

.country-input {
  text-transform: uppercase;
}

.checkbox-field {
  align-content: center;
}

.checkbox-field input {
  height: 18px;
  margin: 3px 0 0;
  width: 18px;
}

.actions {
  display: flex;
  justify-content: flex-end;
}
</style>
