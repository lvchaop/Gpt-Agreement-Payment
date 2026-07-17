<script setup lang="ts">
import { Search, X } from "@lucide/vue";
import { computed, ref, watch } from "vue";

import type { OptionItem } from "../api/types";

const props = withDefaults(defineProps<{
  modelValue: string | string[];
  loader: (query: string) => Promise<OptionItem[]>;
  placeholder?: string;
  multiple?: boolean;
}>(), { placeholder: "搜索并选择", multiple: false });
const emit = defineEmits<{ "update:modelValue": [value: string | string[]] }>();

const query = ref("");
const options = ref<OptionItem[]>([]);
const known = ref(new Map<string, OptionItem>());
const open = ref(false);
const loading = ref(false);
let timer: number | undefined;

const values = computed(() => Array.isArray(props.modelValue) ? props.modelValue : props.modelValue ? [props.modelValue] : []);
const selected = computed(() => values.value.map((value) => known.value.get(value) ?? { value, label: value }));

async function load() {
  loading.value = true;
  try {
    options.value = await props.loader(query.value.trim());
    const next = new Map(known.value);
    options.value.forEach((option) => next.set(option.value, option));
    known.value = next;
  } finally { loading.value = false; }
}

watch(query, () => {
  if (timer) window.clearTimeout(timer);
  timer = window.setTimeout(load, 180);
});
watch(() => props.modelValue, (value) => {
  if (!props.multiple && !value) query.value = "";
});

function focus() { open.value = true; void load(); }
function closeLater() { window.setTimeout(() => { open.value = false; }, 160); }
function choose(option: OptionItem) {
  known.value = new Map(known.value).set(option.value, option);
  if (props.multiple) {
    if (!values.value.includes(option.value)) emit("update:modelValue", [...values.value, option.value]);
    query.value = "";
  } else {
    emit("update:modelValue", option.value); query.value = option.label; open.value = false;
  }
}
function remove(value: string) {
  const next = values.value.filter((item) => item !== value);
  emit("update:modelValue", props.multiple ? next : "");
  if (!props.multiple) query.value = "";
}
</script>

<template>
  <div class="entity-select">
    <div v-if="multiple && selected.length" class="selected-list">
      <span v-for="item in selected" :key="item.value">{{ item.label }}<button type="button" :title="`移除 ${item.label}`" @click="remove(item.value)"><X :size="12" /></button></span>
    </div>
    <label class="search-box">
      <Search :size="15" />
      <input v-model="query" :placeholder="placeholder" @focus="focus" @blur="closeLater" />
      <button v-if="!multiple && values.length" type="button" title="清空选择" @click="remove(values[0])"><X :size="14" /></button>
    </label>
    <div v-if="open" class="option-list">
      <button v-for="option in options" :key="option.value" type="button" @mousedown.prevent="choose(option)">
        <span><strong>{{ option.label }}</strong><small v-if="option.description">{{ option.description }}</small></span>
        <small>{{ option.status }}</small>
      </button>
      <span v-if="loading" class="option-state">加载中...</span>
      <span v-else-if="!options.length" class="option-state">没有匹配项</span>
    </div>
  </div>
</template>

<style scoped>
.entity-select { min-width: 0; position: relative; }
.search-box { align-items: center; background: var(--input-bg); border: 1px solid var(--border-strong); border-radius: var(--radius-sm); display: flex; gap: 7px; min-height: 36px; padding: 0 9px; }
.search-box:focus-within { border-color: var(--accent); box-shadow: 0 0 0 2px var(--accent-soft); }
.search-box svg { color: var(--text-faint); flex: 0 0 auto; }.search-box input { background: transparent; border: 0; color: var(--text-primary); min-width: 0; outline: 0; width: 100%; }.search-box button, .selected-list button { align-items: center; background: transparent; color: var(--text-faint); cursor: pointer; display: inline-flex; padding: 1px; }
.option-list { background: var(--panel-bg-2); border: 1px solid var(--border-strong); border-radius: var(--radius-sm); box-shadow: var(--shadow); left: 0; max-height: 260px; overflow: auto; position: absolute; right: 0; top: calc(100% + 4px); z-index: 80; }
.option-list > button { align-items: center; background: transparent; color: var(--text-primary); cursor: pointer; display: flex; gap: 8px; justify-content: space-between; padding: 8px 10px; text-align: left; width: 100%; }.option-list > button:hover { background: var(--accent-soft); }.option-list strong, .option-list small { display: block; }.option-list strong { font-size: 12px; }.option-list small { color: var(--text-faint); font-size: 10px; margin-top: 2px; }.option-state { color: var(--text-muted); display: block; font-size: 11px; padding: 12px; text-align: center; }
.selected-list { display: flex; flex-wrap: wrap; gap: 5px; margin-bottom: 6px; }.selected-list > span { align-items: center; background: var(--accent-soft); border: 1px solid rgba(75, 145, 232, .35); border-radius: 4px; color: #cfe5ff; display: inline-flex; font-size: 11px; gap: 5px; max-width: 100%; padding: 4px 6px; }.selected-list > span > button { flex: 0 0 auto; }
</style>
