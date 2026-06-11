export type AdminSessionContext = {
  session_id: string;
  user_id: string;
  user_email: string;
  user_display_name?: string | null;
  mode: string;
  status: string;
  season_id?: string | null;
  season_title?: string | null;
  topic_id?: string | null;
  topic_name?: string | null;
  topic_label?: string | null;
  primary_topic?: string | null;
  setup_surface?: string | null;
  target_part?: number | null;
  started_at?: string | null;
  completed_at?: string | null;
  created_at: string;
  updated_at: string;
};

export type AdminUserContext = {
  user_id: string;
  user_hash: string;
  user_email: string;
  user_display_name?: string | null;
  created_at: string;
  updated_at: string;
};

type UserLikeContext = Pick<AdminSessionContext, "user_id" | "user_email" | "user_display_name"> | Pick<AdminUserContext, "user_id" | "user_email" | "user_display_name">;

export function displayUserName(context?: UserLikeContext | null) {
  return context?.user_display_name?.trim() || context?.user_email?.trim() || context?.user_id?.trim() || "";
}

export function displayUserMeta(context?: UserLikeContext | null) {
  const parts = [context?.user_email?.trim(), context?.user_id?.trim()].filter(Boolean);
  return parts.length ? parts.join(" · ") : "";
}

export function formatModeLabel(mode?: string | null) {
  if (mode === "full_exam") return "完整模拟";
  if (mode === "part_practice") return "单项练习";
  if (mode === "topic_practice") return "主题练习";
  return mode?.trim() || "未知模式";
}

export function formatPartLabel(context?: Pick<AdminSessionContext, "target_part" | "mode"> | null) {
  if (context?.target_part) return `Part ${context.target_part}`;
  if (context?.mode === "full_exam") return "Parts 1-3";
  return "未指定题型";
}

export function displayQuestionBankLabel(context?: AdminSessionContext | null) {
  const label = context?.topic_label?.trim() || context?.topic_name?.trim() || context?.season_title?.trim();
  if (label) return label;
  if (context?.primary_topic?.trim()) return humanizeToken(context.primary_topic);
  if (context?.setup_surface?.trim()) return humanizeToken(context.setup_surface);
  return context?.mode?.trim() ? formatModeLabel(context.mode) : "";
}

export function displaySessionTitle(context?: AdminSessionContext | null, fallbackSessionId?: string | null) {
  const label = displayQuestionBankLabel(context);
  const fallbackId = fallbackSessionId || context?.session_id;
  const moment = displaySessionMoment(context) || legacySessionTitle(fallbackId) || shortId(fallbackId);
  return label ? `${label} · ${moment}` : moment;
}

export function displaySessionMeta(context?: AdminSessionContext | null) {
  if (!context) return "";
  const parts = [context.mode?.trim() ? formatModeLabel(context.mode) : "", context.target_part || context.mode === "full_exam" ? formatPartLabel(context) : "", displaySessionMoment(context)].filter(Boolean);
  return parts.join(" · ");
}

export function displaySessionMoment(context?: AdminSessionContext | null) {
  return formatDateTime(context?.started_at || context?.created_at || null);
}

export function formatDateTime(value?: string | null) {
  if (!value) return "";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString("zh-CN", { hour12: false, month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

export function shortId(value?: string | null) {
  if (!value) return "-";
  return value.length > 16 ? `${value.slice(0, 8)}...${value.slice(-4)}` : value;
}

function legacySessionTitle(value?: string | null) {
  if (!value?.startsWith("web_obs_")) return "";
  return `Legacy Observability Probe · ${shortId(value)}`;
}

export function humanizeToken(value: string) {
  return value
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (char) => char.toUpperCase());
}
