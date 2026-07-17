const DISPLAY_TIME_ZONE = "Asia/Shanghai";

const exactFormatter = new Intl.DateTimeFormat("zh-CN", {
  timeZone: DISPLAY_TIME_ZONE,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hourCycle: "h23",
});

export function parseDate(value: unknown) {
  if (!value) return null;
  const date = new Date(String(value));
  return Number.isNaN(date.getTime()) ? null : date;
}

export function formatDateTime(value: unknown) {
  const date = parseDate(value);
  if (!date) return "-";
  return exactFormatter.format(date).replaceAll("/", "-");
}

export function formatRelativeTime(value: unknown, now = Date.now()) {
  const date = parseDate(value);
  if (!date) return "-";
  const seconds = Math.round((date.getTime() - now) / 1000);
  const absolute = Math.abs(seconds);
  const formatter = new Intl.RelativeTimeFormat("zh-CN", { numeric: "auto" });
  if (absolute < 60) return formatter.format(seconds, "second");
  if (absolute < 3600) return formatter.format(Math.round(seconds / 60), "minute");
  if (absolute < 86400) return formatter.format(Math.round(seconds / 3600), "hour");
  if (absolute < 86400 * 30) return formatter.format(Math.round(seconds / 86400), "day");
  return formatter.format(Math.round(seconds / (86400 * 30)), "month");
}

export function formatDuration(milliseconds: unknown) {
  const value = Number(milliseconds);
  if (!Number.isFinite(value) || value < 0) return "-";
  if (value < 1000) return `${Math.round(value)} ms`;
  const seconds = value / 1000;
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 1 : 0)} 秒`;
  const minutes = Math.floor(seconds / 60);
  const remaining = Math.round(seconds % 60);
  if (minutes < 60) return `${minutes} 分 ${remaining} 秒`;
  const hours = Math.floor(minutes / 60);
  return `${hours} 小时 ${minutes % 60} 分`;
}
