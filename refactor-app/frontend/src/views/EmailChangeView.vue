<script setup lang="ts">
import { FileUp, Play, X } from "@lucide/vue";
import { computed, ref } from "vue";
import { useRouter } from "vue-router";

import { resourcesApi } from "../api/resources";
import PageHeader from "../components/PageHeader.vue";
import { useOpsStore } from "../stores/ops";

const router = useRouter();
const store = useOpsStore();
const fileInput = ref<HTMLInputElement | null>(null);
const mode = ref<"mapped_csv" | "source_jsonl_auto_claim">("mapped_csv");
const fileNames = ref<string[]>([]);
const csvText = ref("");
const sourceJsonlText = ref("");
const workCount = ref(5);
const otpTimeoutS = ref(180);
const submitting = ref(false);
const selected = computed(() =>
  mode.value === "mapped_csv"
    ? Boolean(csvText.value.trim())
    : Boolean(sourceJsonlText.value.trim()),
);
const sourceRecordCount = computed(() =>
  sourceJsonlText.value.split(/\r?\n/).filter((line) => line.trim()).length,
);

async function selectFile(event: Event) {
  const input = event.target as HTMLInputElement;
  const files = Array.from(input.files ?? []);
  if (!files.length) return;
  try {
    if (mode.value === "mapped_csv") {
      csvText.value = await files[0].text();
      sourceJsonlText.value = "";
      fileNames.value = [files[0].name];
      return;
    }
    const contents = await Promise.all(files.map((file) => file.text()));
    sourceJsonlText.value = contents.map((item) => item.trim()).filter(Boolean).join("\n");
    csvText.value = "";
    fileNames.value = files.map((file) => file.name);
  } catch (err) {
    clearFile();
    store.toast("读取账号文件失败", String((err as Error).message ?? err), "error");
  }
}

function clearFile() {
  csvText.value = "";
  sourceJsonlText.value = "";
  fileNames.value = [];
  if (fileInput.value) fileInput.value.value = "";
}

function setMode(nextMode: "mapped_csv" | "source_jsonl_auto_claim") {
  if (mode.value === nextMode) return;
  mode.value = nextMode;
  clearFile();
}

async function submitJob() {
  if (!selected.value) {
    store.toast("未选择文件", "请选择换绑所需文件。", "warning");
    return;
  }
  submitting.value = true;
  try {
    const result = await resourcesApi.createAccountEmailChangeJob({
      mode: mode.value,
      csv_text: csvText.value,
      source_jsonl_text: sourceJsonlText.value,
      work_count: Math.max(1, Number(workCount.value || 1)),
      otp_timeout_s: Math.max(1, Number(otpTimeoutS.value || 180)),
      mail_provider: "outlook",
      project_key: "",
      caller_id: "refactor-app-protocol-registration",
      created_by: "ops-ui",
    });
    store.toast(
      "换绑任务已创建",
      `账号=${result.selected_count} Work=${result.work_count}`,
      "success",
    );
    await router.push({ name: "job-trace", params: { jobId: result.job_id } });
  } catch (err) {
    store.toast("创建换绑任务失败", String((err as Error).message ?? err), "error");
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <div>
    <PageHeader
      title="换绑邮箱"
      description="将已注册账号换绑到指定邮箱，或从邮箱池自动领取未使用邮箱。"
    />

    <section class="panel email-change-panel">
      <div class="mode-control" role="group" aria-label="换绑模式">
        <button
          type="button"
          :class="{ active: mode === 'mapped_csv' }"
          @click="setMode('mapped_csv')"
        >
          CSV 指定邮箱
        </button>
        <button
          type="button"
          :class="{ active: mode === 'source_jsonl_auto_claim' }"
          @click="setMode('source_jsonl_auto_claim')"
        >
          账号文件自动领取
        </button>
      </div>
      <div class="form-grid">
        <div class="file-field">
          <span>{{ mode === "mapped_csv" ? "CSV 文件" : "账号文件" }}</span>
          <input
            ref="fileInput"
            class="file-input"
            type="file"
            :accept="mode === 'mapped_csv' ? '.csv,text/csv' : '.txt,.json,.jsonl,text/plain,application/json'"
            :multiple="mode === 'source_jsonl_auto_claim'"
            @change="selectFile"
          />
          <button class="btn" type="button" @click="fileInput?.click()">
            <FileUp :size="16" />{{ mode === "mapped_csv" ? "选择 CSV" : "选择账号文件" }}
          </button>
        </div>
        <label>
          <span>同时 Work 数</span>
          <input v-model.number="workCount" class="input" type="number" min="1" max="500" />
        </label>
        <label>
          <span>新邮箱 OTP 超时（秒）</span>
          <input v-model.number="otpTimeoutS" class="input" type="number" min="1" />
        </label>
      </div>

      <div v-if="fileNames.length" class="selected-file">
        <div>
          <strong>{{ fileNames.length === 1 ? fileNames[0] : `${fileNames.length} 个文件` }}</strong>
          <span v-if="mode === 'mapped_csv'">字段：old_mail, new_mail</span>
          <span v-else>{{ sourceRecordCount }} 条账号记录 · 新邮箱来源：Outlook 邮箱池</span>
        </div>
        <button class="icon-btn" type="button" title="移除文件" @click="clearFile">
          <X :size="16" />
        </button>
      </div>
    </section>

    <div class="actions">
      <button class="btn primary" :disabled="!selected || submitting" @click="submitJob">
        <Play :size="16" />{{ submitting ? "创建中..." : "创建换绑任务" }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.email-change-panel {
  padding: 16px;
}

.mode-control {
  background: var(--panel-bg-2);
  border: 1px solid var(--border);
  display: inline-grid;
  grid-template-columns: repeat(2, minmax(150px, 1fr));
  margin-bottom: 14px;
  padding: 3px;
}

.mode-control button {
  background: transparent;
  border: 0;
  color: var(--text-muted);
  cursor: pointer;
  font: inherit;
  font-size: 13px;
  font-weight: 700;
  min-height: 34px;
  padding: 0 12px;
}

.mode-control button.active {
  background: var(--accent);
  color: white;
}

.form-grid {
  display: grid;
  gap: 12px;
  grid-template-columns: minmax(280px, 1.5fr) repeat(2, minmax(190px, 1fr));
}

label {
  display: grid;
  gap: 6px;
}

label > span,
.selected-file span {
  color: var(--text-muted);
  font-size: 12px;
  font-weight: 700;
}

.file-field {
  align-content: start;
}

.file-field .btn {
  justify-self: start;
  min-height: 38px;
}

.file-input {
  display: none;
}

.selected-file {
  align-items: center;
  background: var(--panel-bg-2);
  border: 1px solid var(--border);
  border-radius: 5px;
  display: flex;
  justify-content: space-between;
  margin-top: 14px;
  min-height: 54px;
  padding: 9px 11px;
}

.selected-file strong,
.selected-file span {
  display: block;
}

.selected-file strong {
  font-size: 13px;
  margin-bottom: 3px;
}

.actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 14px;
}

@media (max-width: 900px) {
  .form-grid {
    grid-template-columns: 1fr;
  }
}
</style>
