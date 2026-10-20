import type { ApplicationStatus } from "../types";

const kzt = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 });

export const formatKzt = (value: number) => `${kzt.format(value)} ₸`;

export const formatHa = (value: number) =>
  `${value.toLocaleString("ru-RU", { maximumFractionDigits: 1 })} га`;

export const formatDate = (iso: string) =>
  new Date(iso).toLocaleDateString("ru-RU", { day: "numeric", month: "long", year: "numeric" });

export const STATUS_LABEL: Record<ApplicationStatus, string> = {
  pending: "В очереди",
  processing: "Анализируем поле",
  approved: "Одобрено",
  review: "На проверке у аналитика",
  rejected: "Отказ",
  error: "Техническая ошибка",
};

export const CATEGORY_LABEL: Record<string, string> = {
  seeds: "Семена",
  fertilizer: "Удобрения",
  protection: "Защита растений",
};

export const CLASS_LABEL: Record<string, string> = {
  A: "Низкий риск",
  B: "Средний риск",
  C: "Высокий риск",
};
