<script setup lang="ts">
import { X } from "@lucide/vue";

withDefaults(defineProps<{
  open: boolean;
  title: string;
  description?: string;
  busy?: boolean;
  submitText?: string;
  width?: "normal" | "wide";
}>(), { description: "", busy: false, submitText: "保存", width: "normal" });

const emit = defineEmits<{ close: []; submit: [] }>();
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="drawer-layer">
      <div class="drawer-scrim" @click="emit('close')" />
      <aside class="drawer" :class="width" role="dialog" aria-modal="true" :aria-label="title">
        <header>
          <div><h2>{{ title }}</h2><p v-if="description">{{ description }}</p></div>
          <button class="icon-btn" title="关闭" @click="emit('close')"><X :size="17" /></button>
        </header>
        <form @submit.prevent="emit('submit')">
          <div class="drawer-body"><slot /></div>
          <footer>
            <button class="btn" type="button" :disabled="busy" @click="emit('close')">取消</button>
            <button class="btn primary" type="submit" :disabled="busy">{{ busy ? "处理中..." : submitText }}</button>
          </footer>
        </form>
      </aside>
    </div>
  </Teleport>
</template>

<style scoped>
.drawer-layer { inset: 0; position: fixed; z-index: 60; }
.drawer-scrim { background: rgba(0, 0, 0, 0.58); inset: 0; position: absolute; }
.drawer { background: var(--panel-bg); border-left: 1px solid var(--border-strong); bottom: 0; box-shadow: var(--shadow); display: flex; flex-direction: column; position: absolute; right: 0; top: 0; width: min(480px, 100vw); }
.drawer.wide { width: min(680px, 100vw); }
.drawer > header { align-items: flex-start; border-bottom: 1px solid var(--border); display: flex; gap: 12px; justify-content: space-between; padding: 16px; }
h2 { font-size: 17px; margin: 0; }
p { color: var(--text-muted); font-size: 12px; line-height: 1.45; margin: 5px 0 0; }
form { display: flex; flex: 1; flex-direction: column; min-height: 0; }
.drawer-body { align-content: start; display: grid; flex: 1; gap: 14px; min-height: 0; overflow: auto; padding: 16px; }
footer { align-items: center; border-top: 1px solid var(--border); display: flex; gap: 8px; justify-content: flex-end; padding: 12px 16px; }
</style>
