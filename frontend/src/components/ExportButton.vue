<script setup>
import { Download } from "@lucide/vue";
import { ref } from "vue";
import { downloadBlob } from "../api";

const props = defineProps({
  path: { type: String, required: true },
  filename: { type: String, required: true },
  label: { type: String, default: "导出" },
  disabled: { type: Boolean, default: false },
});
const format = ref("xlsx");
const exporting = ref(false);
const error = ref("");

async function exportFile() {
  if (props.disabled || exporting.value) return;
  exporting.value = true;
  error.value = "";
  const extension = format.value;
  try {
    await downloadBlob(`${props.path}.${extension}`, `${props.filename}.${extension}`);
  } catch (err) {
    let detail = err.response?.data;
    if (detail instanceof Blob) {
      try { detail = JSON.parse(await detail.text()); } catch { detail = null; }
    }
    error.value = detail?.error || "导出失败，请稍后重试";
  } finally {
    exporting.value = false;
  }
}
</script>

<template>
  <div class="space-y-1">
    <div class="flex items-center gap-2">
      <select v-model="format" class="input w-auto" :aria-label="`${label}格式`" :disabled="disabled || exporting">
        <option value="xlsx">Excel (.xlsx)</option>
        <option value="csv">CSV (.csv)</option>
      </select>
      <button type="button" class="btn-secondary whitespace-nowrap" :disabled="disabled || exporting" @click="exportFile">
        <Download class="h-4 w-4" />{{ exporting ? "导出中…" : label }}
      </button>
    </div>
    <p v-if="error" class="max-w-sm text-sm text-red-700" role="alert">{{ error }}</p>
  </div>
</template>
