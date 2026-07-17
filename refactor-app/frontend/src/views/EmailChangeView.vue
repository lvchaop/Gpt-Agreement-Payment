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
const fileName = ref("");
const csvText = ref("");
const workCount = ref(5);
const otpTimeoutS = ref(180);
const submitting = ref(false);
const selected = computed(() => Boolean(csvText.value.trim()));

async function selectFile(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;
  try {
    csvText.value = await file.text();
    fileName.value = file.name;
  } catch (err) {
    clearFile();
    store.toast("读取 CSV 失败", String((err as Error).message ?? err), "error");
  }
}

function clearFile() {
  csvText.value = "";
  fileName.value = "";
  if (fileInput.value) fileInput.value.value = "";
}

async function submitJob() {
  if (!selected.value) {
    store.toast("未选择 CSV", "请选择换绑邮箱 CSV。", "warning");
    return;
  }
  submitting.value = true;
  try {
    const result = await resourcesApi.createAccountEmailChangeJob({
      csv_text: csvText.value,
      work_count: Math.max(1, Number(workCount.value || 1)),
      otp_timeout_s: Math.max(1, Number(otpTimeoutS.value || 180)),
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
      description="按 CSV 行将已注册账号换绑到对应的新邮箱。"
    />

    <section class="panel email-change-panel">
      <div class="form-grid">
        <div class="file-field">
          <span>CSV 文件</span>
          <input
            ref="fileInput"
            class="file-input"
            type="file"
            accept=".csv,text/csv"
            @change="selectFile"
          />
          <button class="btn" type="button" @click="fileInput?.click()">
            <FileUp :size="16" />选择 CSV
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

      <div v-if="fileName" class="selected-file">
        <div>
          <strong>{{ fileName }}</strong>
          <span>字段：old_mail, new_mail</span>
        </div>
        <button class="icon-btn" type="button" title="移除 CSV" @click="clearFile">
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
