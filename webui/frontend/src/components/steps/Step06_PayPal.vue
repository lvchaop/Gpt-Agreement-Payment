<template>
  <section class="step-fade-in">
    <template v-if="store.isStepHidden(6)">
      <div class="term-divider" data-tail="──────────">步骤 06: PayPal — 已跳过</div>
      <h2 class="step-h">$&nbsp;此步已跳过<span class="term-cursor"></span></h2>
      <p class="step-sub">你在 step 1 选了"纯卡"支付，PayPal 配置不需要。</p>
      <div class="step-actions">
        <button class="term-btn term-btn--ghost" @click="goStep1">返回 step 1 修改</button>
      </div>
    </template>
    <template v-else>
      <div class="term-divider" data-tail="──────────">步骤 06: PayPal</div>
      <h2 class="step-h">$&nbsp;PayPal 链路<span class="term-cursor"></span></h2>
      <p v-if="isNewUserFlow" class="step-sub">新用户链路运行时生成 PayPal 身份，手机号走手机号池，地址实时取 meiguodizhi。</p>
      <p v-else class="step-sub">老账号链路使用已存在的 PayPal 邮箱、密码或 cookies。</p>

      <div class="form-stack">
        <TermChoice v-model="form.flow" :options="flowOptions" :cols="2" />
        <TermField v-model="form.country" label="PayPal 地区 · country" placeholder="US" />
        <template v-if="isNewUserFlow">
          <TermToggle v-model="form.visible_browser">验证码时显示浏览器窗口</TermToggle>
          <TermToggle v-model="form.node_rpa">Node RPA 真实浏览器 PayPal</TermToggle>
          <TermToggle v-if="form.node_rpa" v-model="form.node_rpa_headless">Node RPA headless</TermToggle>
          <TermToggle v-model="form.sms_api_enabled">短信接口自动取码</TermToggle>
          <TermField v-model="form.phones_file" label="手机号池 · phones_file" placeholder="output/paypal_test_phones.jsonl" />
          <TermField v-model="form.cards_file" label="测试卡池 · cards_file" placeholder="留空则使用 Step 07/cards" />
          <TermField v-model.number="form.manual_otp_timeout_s" label="portal 手动 OTP 等待秒数" type="number" />
          <TermField v-if="form.node_rpa" v-model.number="form.node_rpa_timeout_s" label="Node RPA 总超时秒数" type="number" />
          <TermField v-if="form.node_rpa" v-model.number="form.fallback_consent_delay_ms" label="Agree 前等待毫秒" type="number" />
          <TermField v-model.number="form.manual_recaptcha_timeout_s" label="reCAPTCHA 人工等待秒数" type="number" />
        </template>
        <template v-else>
          <TermField v-model="form.email" label="PayPal 邮箱 · email" placeholder="必须是 catch-all zone 内的地址" />
          <TermField v-model="form.password" label="PayPal 密码 · password" type="password" />
        </template>
      </div>

      <div v-if="warning" class="result-block result--warn" style="margin-top:16px">
        <div class="result-head">
          <span class="result-icon">▲</span>
          <span>{{ warning }}</span>
        </div>
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { ref, computed, watch } from "vue";
import { useWizardStore } from "../../stores/wizard";
import TermField from "../term/TermField.vue";
import TermChoice from "../term/TermChoice.vue";
import TermToggle from "../term/TermToggle.vue";

const store = useWizardStore();
const init = store.answers.paypal ?? {};
const form = ref({
  flow: init.flow ?? "existing_account",
  email: init.email ?? "",
  password: init.password ?? "",
  country: init.country ?? "US",
  phones_file: init.phones_file ?? "output/paypal_test_phones.jsonl",
  cards_file: init.cards_file ?? "",
  visible_browser: init.visible_browser ?? false,
  node_rpa: init.node_rpa ?? false,
  node_rpa_headless: init.node_rpa_headless ?? false,
  node_rpa_timeout_s: init.node_rpa_timeout_s ?? 720,
  fallback_consent_delay_ms: init.fallback_consent_delay_ms ?? 12000,
  sms_api_enabled: init.sms_api_enabled ?? false,
  manual_otp_timeout_s: init.manual_otp_timeout_s ?? 600,
  manual_recaptcha_timeout_s: init.manual_recaptcha_timeout_s ?? 300,
});

const flowOptions = [
  { value: "existing_account", label: "existing_account", desc: "老 PayPal 账号登录" },
  { value: "new_user", label: "new_user", desc: "PayPal 新用户 / guest checkout" },
];

const flowMode = computed(() => form.value.flow.trim().toLowerCase().replace("-", "_"));
const isNewUserFlow = computed(() => flowMode.value !== "existing_account");

const warning = computed(() => {
  const flow = flowMode.value;
  if (!["existing_account", "new_user", "sandbox_new_user"].includes(flow)) return "flow 只能是 existing_account / new_user / sandbox_new_user";
  if (flow === "existing_account" && form.value.email && !form.value.email.includes("@")) return "邮箱格式不对";
  if (flow === "existing_account" && form.value.password && form.value.password.length < 6) return "密码看着太短了";
  if (flow !== "existing_account" && !form.value.phones_file.trim()) return "新用户模式需要手机号池文件";
  const country = form.value.country.trim().toUpperCase();
  if (country && !/^[A-Z]{2}$/.test(country)) return "地区需要填两位国家代码，比如 US";
  return null;
});

watch(form, () => {
  store.setAnswer("paypal", form.value);
  store.saveToServer();
}, { deep: true });

function goStep1() {
  store.setStep(1);
  store.saveToServer();
}
</script>
