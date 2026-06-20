import { defineStore } from "pinia";

type ToastTone = "success" | "error" | "info" | "warning";

export type Toast = {
  id: string;
  title: string;
  message: string;
  tone: ToastTone;
};

export const useOpsStore = defineStore("ops", {
  state: () => ({
    toasts: [] as Toast[],
    lastRefresh: "",
  }),
  actions: {
    toast(title: string, message: string, tone: ToastTone = "info") {
      const id = crypto.randomUUID();
      this.toasts.push({ id, title, message, tone });
      window.setTimeout(() => this.dismissToast(id), 5000);
    },
    dismissToast(id: string) {
      this.toasts = this.toasts.filter((toast) => toast.id !== id);
    },
    touchRefresh() {
      this.lastRefresh = new Date().toLocaleTimeString();
    },
  },
});
