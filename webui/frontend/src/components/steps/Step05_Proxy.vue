<template>
  <section class="step-fade-in">
    <div class="term-divider" data-tail="──────────">步骤 05: 代理</div>
    <h2 class="step-h">$&nbsp;代理<span class="term-cursor"></span></h2>
    <p class="step-sub">PayPal 锁地区，Stripe 锁国家。出口必须在 EU/US。</p>

    <TermChoice
      v-model="form.mode"
      :options="modeOptions"
      :cols="4"
    />

    <div v-if="form.mode === 'webshare'" style="margin-top:16px">
      <div class="info-block">
        <p>
          <strong>Webshare 模式 = 代理 + 12 路自愈</strong>。pipeline 在 daemon 模式下会自动:
        </p>
        <ul class="info-list">
          <li>累计 N 次 <code>no_invite_permission</code> 触发换 IP（webshare API rotate）</li>
          <li>同 zone 换够 IP 后自动切 CF zone</li>
          <li>注册连续失败也切 zone</li>
          <li>配额耗尽进 N 小时冷却</li>
          <li>本地 gost 中继挂掉看门狗自动拉起</li>
          <li>换 IP 后同步 gpt-team 全局代理</li>
        </ul>
        <p style="margin-top:8px">
          多数情况用默认参数即可，下方"高级"里能调阈值。详见 <code>docs/daemon-mode.md</code> 12 路自愈环。
        </p>
      </div>

      <div class="form-stack">
        <TermField v-model="form.api_key" label="Webshare API Key · api_key" type="password" />
        <TermField v-model="form.lock_country" label="锁出口国 · lock_country" placeholder="US (锁出口国)" />
      </div>

      <div class="step-actions">
        <TermBtn :loading="loading" @click="testWebshare">测试 Webshare</TermBtn>
        <button class="advanced-toggle" @click="showAdvanced = !showAdvanced">
          {{ showAdvanced ? '▾' : '▸' }} 高级（轮换阈值 / gost / 下游同步）
        </button>
      </div>

      <div v-if="showAdvanced" class="form-stack" style="margin-top:12px">
        <TermField v-model.number="form.refresh_threshold" label="换 IP 阈值 · refresh_threshold" type="number" placeholder="2 (累计 N 次 no_perm 后换 IP)" />
        <TermField v-model.number="form.zone_rotate_after_ip_rotations" label="切 zone IP 轮换数 · zone_rotate_after_ip_rotations" type="number" placeholder="2 (同 zone 换 N 次 IP 后切 zone)" />
        <TermField v-model.number="form.zone_rotate_on_reg_fails" label="切 zone 注册失败数 · zone_rotate_on_reg_fails" type="number" placeholder="3 (连续 N 次注册失败切 zone)" />
        <TermField v-model.number="form.no_rotation_cooldown_s" label="配额冷却秒数 · no_rotation_cooldown_s" type="number" placeholder="10800 (配额耗尽冷却秒数)" />
        <TermField v-model.number="form.gost_listen_port" label="gost 中继端口 · gost_listen_port" type="number" placeholder="18898 (本地 gost 中继端口)" />
        <label class="toggle-row">
          <input type="checkbox" v-model="form.sync_team_proxy" />
          <span>换 IP 后同步 gpt-team 全局代理 (sync_team_proxy)</span>
        </label>
      </div>
    </div>

    <div v-if="form.mode === 'manual'" class="form-stack" style="margin-top:16px">
      <TermField v-model="form.url" label="代理 URL · url" placeholder="socks5://user:pw@host:port" />
      <TermField v-model="form.expected_country" label="期望国家 · expected_country" placeholder="US" />
      <div class="step-actions">
        <TermBtn :loading="loading" @click="testProxy">测试出口 IP</TermBtn>
      </div>
    </div>

    <div v-if="form.mode === 'trojan-pool'" style="margin-top:16px">
      <div class="info-block">
        <p><strong>Trojan 池模式</strong>会用 sing-box 把 <code>trojan://</code> 节点转成本地 HTTP 代理，并按阶段选择地区。</p>
        <ul class="info-list">
          <li><code>register</code> 写入注册配置</li>
          <li><code>checkout</code> 写入 <code>fresh_checkout.proxy</code></li>
          <li><code>payment</code> 写入支付、Stripe stages、PayPal、solver</li>
        </ul>
      </div>

      <div class="form-stack">
        <TermField v-model="form.trojan_pool_file" label="Trojan 池文件 · trojan_pool_file" placeholder="output/trojan_pool.txt" />
        <TermField v-model.number="form.trojan_http_start_port" label="本地 HTTP 起始端口 · trojan_http_start_port" type="number" placeholder="18081" />
        <TermField v-model="form.trojan_bridge_bin" label="sing-box 路径 · trojan_bridge_bin" placeholder="sing-box" />
        <TermField v-model="form.proxy_region_all" label="默认地区 · proxy_region_all" placeholder="US" />
        <TermField v-model="form.proxy_region_register" label="注册地区 · proxy_region_register" placeholder="US" />
        <TermField v-model="form.proxy_region_checkout" label="checkout 地区 · proxy_region_checkout" placeholder="US" />
        <TermField v-model="form.proxy_region_payment" label="支付地区 · proxy_region_payment" placeholder="HK" />
      </div>

      <div class="step-actions">
        <TermBtn :loading="bridgeLoading" @click="startTrojan">启动 Trojan Bridge</TermBtn>
        <TermBtn :loading="bridgeLoading" @click="stopTrojan">停止</TermBtn>
        <TermBtn :loading="bridgeLoading" @click="refreshTrojan">刷新状态</TermBtn>
        <TermBtn :loading="bridgeLoading" @click="loadTrojanNodes">解析节点</TermBtn>
      </div>

      <div v-if="bridgeStatus" class="bridge-panel">
        <div class="bridge-head">
          <span :class="bridgeStatus.running ? 'ok-dot' : 'fail-dot'"></span>
          <span>{{ bridgeStatus.running ? 'bridge running' : 'bridge stopped' }}</span>
          <code v-if="bridgeStatus.pid">pid={{ bridgeStatus.pid }}</code>
        </div>
        <div v-if="bridgeStatus.nodes?.length" class="node-grid">
          <div v-for="node in bridgeStatus.nodes" :key="node.url || node.port" class="node-row">
            <span>{{ node.region || node.outbound || node.tag || '-' }}</span>
            <code>{{ node.url }}</code>
            <span :class="node.open ? 'ok-text' : 'fail-text'">{{ node.open ? 'open' : 'closed' }}</span>
          </div>
        </div>
      </div>
    </div>

    <div v-if="result" class="result-block" :class="`result--${result.status}`">
      <div class="result-head">
        <span class="result-icon">{{ icon(result.status) }}</span>
        <span>{{ result.message }}</span>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import { useWizardStore } from "../../stores/wizard";
import type { PreflightResult } from "../../api/client";
import { api } from "../../api/client";
import TermField from "../term/TermField.vue";
import TermBtn from "../term/TermBtn.vue";
import TermChoice from "../term/TermChoice.vue";

const store = useWizardStore();
const init = store.answers.proxy ?? {};
const form = ref({
  mode: init.mode ?? "manual",
  url: init.url ?? "",
  expected_country: init.expected_country ?? "US",
  api_key: init.api_key ?? "",
  lock_country: init.lock_country ?? "US",
  // webshare 高级（默认值跟 pipeline.py 一致）
  refresh_threshold: init.refresh_threshold ?? 2,
  zone_rotate_after_ip_rotations: init.zone_rotate_after_ip_rotations ?? 2,
  zone_rotate_on_reg_fails: init.zone_rotate_on_reg_fails ?? 3,
  no_rotation_cooldown_s: init.no_rotation_cooldown_s ?? 10800,
  gost_listen_port: init.gost_listen_port ?? 18898,
  sync_team_proxy: init.sync_team_proxy ?? true,
  trojan_pool_file: init.trojan_pool_file ?? "output/trojan_pool.txt",
  trojan_http_start_port: init.trojan_http_start_port ?? 18081,
  trojan_bridge_bin: init.trojan_bridge_bin ?? "sing-box",
  proxy_region_all: init.proxy_region_all ?? "",
  proxy_region_register: init.proxy_region_register ?? "US",
  proxy_region_checkout: init.proxy_region_checkout ?? "US",
  proxy_region_payment: init.proxy_region_payment ?? "",
});
const loading = ref(false);
const bridgeLoading = ref(false);
const result = ref<PreflightResult | null>(null);
const showAdvanced = ref(false);
const bridgeStatus = ref<any | null>(null);

const modeOptions = [
  { value: "webshare", label: "webshare", desc: "Webshare API 托管 + 12 路自愈" },
  { value: "trojan-pool", label: "trojan", desc: "Trojan 池 + 按阶段地区" },
  { value: "manual", label: "manual", desc: "手动 socks5/http" },
  { value: "none", label: "none", desc: "不用代理（直连）" },
];

async function testProxy() {
  store.setAnswer("proxy", form.value);
  await store.saveToServer();
  loading.value = true;
  try {
    result.value = await store.runPreflight("proxy", {
      mode: form.value.mode,
      url: form.value.url,
      expected_country: form.value.expected_country,
    });
  } finally { loading.value = false; }
}

async function testWebshare() {
  store.setAnswer("proxy", form.value);
  await store.saveToServer();
  loading.value = true;
  try {
    result.value = await store.runPreflight("webshare", { api_key: form.value.api_key });
  } finally { loading.value = false; }
}

function trojanBody() {
  return {
    pool_file: form.value.trojan_pool_file,
    http_start_port: Number(form.value.trojan_http_start_port || 18081),
    bridge_bin: form.value.trojan_bridge_bin || "sing-box",
    auto_start: true,
  };
}

async function startTrojan() {
  store.setAnswer("proxy", form.value);
  await store.saveToServer();
  bridgeLoading.value = true;
  try {
    const r = await api.post("/proxy/trojan/start", trojanBody());
    bridgeStatus.value = r.data;
  } finally { bridgeLoading.value = false; }
}

async function stopTrojan() {
  bridgeLoading.value = true;
  try {
    const r = await api.post("/proxy/trojan/stop");
    bridgeStatus.value = r.data;
  } finally { bridgeLoading.value = false; }
}

async function refreshTrojan() {
  bridgeLoading.value = true;
  try {
    const r = await api.get("/proxy/trojan/status");
    bridgeStatus.value = r.data;
  } finally { bridgeLoading.value = false; }
}

async function loadTrojanNodes() {
  bridgeLoading.value = true;
  try {
    const r = await api.get("/proxy/trojan/nodes", {
      params: {
        pool_file: form.value.trojan_pool_file,
        http_start_port: form.value.trojan_http_start_port,
      },
    });
    bridgeStatus.value = {
      ...(bridgeStatus.value || {}),
      nodes: r.data.nodes,
      running: Boolean(bridgeStatus.value?.running),
    };
  } finally { bridgeLoading.value = false; }
}

watch(form, () => store.setAnswer("proxy", form.value), { deep: true });
onMounted(() => { refreshTrojan().catch(() => {}); });

function icon(s: string) {
  return s === "ok" ? "✓" : s === "fail" ? "✗" : s === "warn" ? "▲" : "○";
}
</script>

<style scoped>
.info-block {
  background: var(--bg-panel);
  border-left: 3px solid var(--accent);
  padding: 10px 14px;
  margin: 0 0 16px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--fg-secondary);
}
.info-block p { margin: 0; }
.info-block strong { color: var(--fg-primary); font-weight: 700; }
.info-list { margin: 6px 0 0 18px; padding: 0; }
.info-list li { margin: 3px 0; }
code {
  background: var(--bg-base);
  padding: 1px 5px;
  border: 1px solid var(--border);
  font-size: 11px;
}
.advanced-toggle {
  background: transparent;
  border: 0;
  color: var(--fg-secondary);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
  padding: 8px 0;
}
.advanced-toggle:hover { color: var(--accent); }
.toggle-row { display: flex; align-items: center; gap: 8px; cursor: pointer; padding: 8px 0; font-size: 13px; }
.toggle-row input { accent-color: var(--accent); }
.bridge-panel {
  margin-top: 12px;
  border: 1px solid var(--border);
  background: var(--bg-panel);
  padding: 10px 12px;
}
.bridge-head {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--fg-primary);
}
.ok-dot,
.fail-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
}
.ok-dot { background: #16a34a; }
.fail-dot { background: #dc2626; }
.node-grid { margin-top: 10px; display: grid; gap: 6px; }
.node-row {
  display: grid;
  grid-template-columns: minmax(52px, 0.5fr) minmax(180px, 2fr) minmax(52px, 0.5fr);
  gap: 8px;
  align-items: center;
  font-size: 12px;
}
.node-row code {
  overflow-wrap: anywhere;
}
.ok-text { color: #16a34a; }
.fail-text { color: #dc2626; }
</style>
