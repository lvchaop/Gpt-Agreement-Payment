<template>
  <section class="step-fade-in">
    <div class="term-divider" data-tail="──────────">步骤 11: 下游推送</div>
    <h2 class="step-h">$&nbsp;下游推送 (全部可选)<span class="term-cursor"></span></h2>

    <div class="term-divider" style="margin-top:8px">gpt-team</div>
    <TermToggle v-model="ts.enabled">启用 gpt-team</TermToggle>
    <div v-if="ts.enabled" class="form-stack" style="margin-top:12px">
      <TermField v-model="ts.base_url" label="Base URL · base_url" />
      <TermField v-model="ts.username" label="用户名 · username" />
      <TermField v-model="ts.password" label="密码 · password" type="password" />
      <div class="step-actions">
        <TermBtn :loading="tsLoading" @click="testTs">登录测试</TermBtn>
      </div>
      <div v-if="tsResult" class="result-block" :class="`result--${tsResult.status}`">
        <div class="result-head">
          <span class="result-icon">{{ icon(tsResult.status) }}</span>
          <span>{{ tsResult.message }}</span>
        </div>
      </div>
    </div>

    <div class="term-divider" style="margin-top:20px">CPA</div>
    <TermToggle v-model="cpa.enabled">启用 CPA</TermToggle>
    <div v-if="cpa.enabled" class="form-stack" style="margin-top:12px">
      <TermSelect
        v-model="cpa.target"
        label="目标 · target"
        :options="[
          { value: 'cpa', label: 'CPA 兼容接口', desc: 'POST /v0/management/auth-files' },
          { value: 'sub2api', label: 'Sub2API', desc: 'POST /api/v1/admin/accounts/import/codex-session' },
        ]"
      />
      <TermField v-model="cpa.base_url" label="Base URL · base_url" />
      <TermField v-model="cpa.admin_key" label="Admin Key · admin_key" type="password" />
      <template v-if="cpa.target === 'sub2api'">
        <TermField v-model="cpa.group_ids" label="分组 IDs · group_ids" placeholder="1,2" />
        <TermField v-model="cpa.proxy_id" label="代理 ID · proxy_id" placeholder="可选" />
        <TermField v-model.number="cpa.concurrency" label="并发 · concurrency" type="number" />
        <TermField v-model.number="cpa.priority" label="优先级 · priority" type="number" />
        <TermToggle v-model="cpa.update_existing">重复账号更新</TermToggle>
      </template>
      <div class="step-actions">
        <TermBtn :loading="cpaLoading" @click="testCpa">健康检查</TermBtn>
      </div>
      <div v-if="cpaResult" class="result-block" :class="`result--${cpaResult.status}`">
        <div class="result-head">
          <span class="result-icon">{{ icon(cpaResult.status) }}</span>
          <span>{{ cpaResult.message }}</span>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref, watch, onMounted } from "vue";
import { useWizardStore } from "../../stores/wizard";
import type { PreflightResult } from "../../api/client";
import TermField from "../term/TermField.vue";
import TermBtn from "../term/TermBtn.vue";
import TermToggle from "../term/TermToggle.vue";
import TermSelect from "../term/TermSelect.vue";

const store = useWizardStore();
const tsInit = store.answers.team_system ?? {};
const cpaInit = store.answers.cpa ?? {};

// 开关默认关闭（不读 init.enabled），但其余字段保留 source 同步的值
// 这样用户启用 toggle 时直接看到预填的 url/凭据
const ts = ref({
  enabled: false,
  base_url: tsInit.base_url ?? "http://127.0.0.1:3000",
  username: tsInit.username ?? "admin",
  password: tsInit.password ?? "",
});
const cpa = ref({
  enabled: false,
  target: cpaInit.target ?? "cpa",
  base_url: cpaInit.base_url ?? "",
  admin_key: cpaInit.admin_key ?? "",
  group_ids: Array.isArray(cpaInit.group_ids) ? cpaInit.group_ids.join(",") : (cpaInit.group_ids ?? ""),
  proxy_id: cpaInit.proxy_id ?? "",
  concurrency: cpaInit.concurrency ?? 1,
  priority: cpaInit.priority ?? 0,
  update_existing: cpaInit.update_existing ?? true,
});

// 立即同步到 store 覆盖可能从 source 同步过来的 enabled=true，
// 否则 UI 显示关但 wizard state / 导出仍会写 enabled=true
onMounted(() => {
  store.setAnswer("team_system", {});
  store.setAnswer("cpa", {});
  store.saveToServer();
});
const tsLoading = ref(false);
const cpaLoading = ref(false);
const tsResult = ref<PreflightResult | null>(null);
const cpaResult = ref<PreflightResult | null>(null);

async function testTs() {
  tsLoading.value = true;
  try {
    tsResult.value = await store.runPreflight("team_system", {
      base_url: ts.value.base_url,
      username: ts.value.username,
      password: ts.value.password,
    });
  } finally { tsLoading.value = false; }
}
async function testCpa() {
  cpaLoading.value = true;
  try {
    cpaResult.value = await store.runPreflight("cpa", {
      target: cpa.value.target,
      base_url: cpa.value.base_url,
      admin_key: cpa.value.admin_key,
    });
  } finally { cpaLoading.value = false; }
}
watch([ts, cpa], () => {
  store.setAnswer("team_system", ts.value.enabled ? ts.value : {});
  store.setAnswer("cpa", cpa.value.enabled ? cpa.value : {});
  store.saveToServer();
}, { deep: true });

function icon(s: string) {
  return s === "ok" ? "✓" : s === "fail" ? "✗" : s === "warn" ? "▲" : "○";
}
</script>
