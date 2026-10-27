import type { ApplicationStatus, DealStatus, Monitoring } from "../types";

const kzt = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 });

export const formatKzt = (value: number) => `${kzt.format(value)} ₸`;

export const formatHa = (value: number) =>
  `${value.toLocaleString("ru-RU", { maximumFractionDigits: 1 })} га`;

export const formatPct = (value: number, digits = 0) =>
  `${(value * 100).toLocaleString("ru-RU", { maximumFractionDigits: digits })}%`;

// Крупные суммы в портфеле: 412,5 млн ₸
export const formatMln = (value: number) =>
  `${(value / 1_000_000).toLocaleString("ru-RU", { maximumFractionDigits: 1 })} млн ₸`;

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

export const DEAL_STATUS_LABEL: Record<DealStatus, string> = {
  contracted: "Договор подписан",
  supplier_paid: "Поставщику оплачено",
  delivered: "Товар отгружен",
  sowing_confirmed: "Сев подтверждён",
  restructured: "Перенос на след. сезон",
  repaid: "Погашено",
};

export const MONITORING_LABEL: Record<Monitoring["status"], string> = {
  no_data: "Нет снимков",
  waiting: "Ждём всходов",
  not_sown: "Не засеяно",
  growing: "Всходы есть",
  normal: "В норме",
  stress: "Риск неурожая",
};
