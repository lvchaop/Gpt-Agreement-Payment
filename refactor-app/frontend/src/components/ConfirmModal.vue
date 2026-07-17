<script setup lang="ts">
import { TriangleAlert, X } from "@lucide/vue";

withDefaults(defineProps<{
  open: boolean;
  title: string;
  message?: string;
  summary?: Record<string, unknown>;
  confirmText?: string;
  danger?: boolean;
  busy?: boolean;
}>(), { message: "", confirmText: "确认", danger: false, busy: false });

const emit = defineEmits<{ close: []; confirm: [] }>();
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="overlay" @click.self="emit('close')">
      <section class="modal" role="alertdialog" aria-modal="true" :aria-label="title">
        <header>
          <span class="modal-icon" :class="{ danger }"><TriangleAlert :size="18" /></span>
          <div><h2>{{ title }}</h2><p v-if="message">{{ message }}</p></div>
          <button class="icon-btn" title="关闭" @click="emit('close')"><X :size="16" /></button>
        </header>
        <dl v-if="summary">
          <template v-for="(value, key) in summary" :key="key">
            <dt>{{ key }}</dt><dd>{{ value }}</dd>
          </template>
        </dl>
        <footer>
          <button class="btn" :disabled="busy" @click="emit('close')">取消</button>
          <button class="btn" :class="{ danger, primary: !danger }" :disabled="busy" @click="emit('confirm')">
            {{ busy ? "处理中..." : confirmText }}
          </button>
        </footer>
      </section>
    </div>
  </Teleport>
</template>

<style scoped>
.overlay { align-items: center; background: rgba(0, 0, 0, 0.62); display: flex; inset: 0; justify-content: center; padding: 20px; position: fixed; z-index: 70; }
.modal { background: var(--panel-bg); border: 1px solid var(--border-strong); border-radius: var(--radius-md); box-shadow: var(--shadow); max-width: 520px; overflow: hidden; width: 100%; }
header { align-items: flex-start; display: flex; gap: 11px; padding: 16px; }
header > div { flex: 1; }
.modal-icon { align-items: center; background: var(--accent-soft); border-radius: 5px; color: var(--accent); display: flex; height: 32px; justify-content: center; width: 32px; }
.modal-icon.danger { background: rgba(215, 91, 91, 0.14); color: var(--danger-text); }
h2 { font-size: 16px; margin: 0; }
p { color: var(--text-muted); font-size: 12px; line-height: 1.5; margin: 5px 0 0; white-space: pre-line; }
dl { border-bottom: 1px solid var(--border); border-top: 1px solid var(--border); display: grid; grid-template-columns: 140px 1fr; margin: 0; }
dt, dd { border-bottom: 1px solid var(--border); margin: 0; padding: 9px 12px; }
dt { color: var(--text-muted); font-size: 11px; font-weight: 700; }
dd { font-size: 12px; overflow-wrap: anywhere; }
dl > :nth-last-child(-n+2) { border-bottom: 0; }
footer { display: flex; gap: 8px; justify-content: flex-end; padding: 12px 16px; }
</style>
