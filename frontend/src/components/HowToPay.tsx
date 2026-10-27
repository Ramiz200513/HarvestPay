// Фермеру: когда и сколько платить, куда переводить и что делать, если урожай подвёл.
// Оплаченная сумма распределяется по платежам графика по порядку — так видно, какой платёж закрыт,
// какой частично, а какой просрочен.
import { useState } from "react";
import { formatDate, formatKzt, formatPct } from "../lib/format";
import type { Deal, PaymentInfo } from "../types";

type PaymentState = "paid" | "partial" | "overdue" | "next" | "later";

interface PlannedPayment {
  date: string;
  amount: number;
  paid: number;
  state: PaymentState;
}

const STATE_LABEL: Record<PaymentState, string> = {
  paid: "оплачен",
  partial: "оплачен частично",
  overdue: "просрочен",
  next: "ближайший",
  later: "позже",
};

function plan(deal: Deal, today = new Date()): PlannedPayment[] {
  let left = deal.paid_amount;
  let nextFound = false;
  const todayIso = today.toISOString().slice(0, 10);
  return deal.schedule.map((p) => {
    const paid = Math.min(p.amount, left);
    left -= paid;
    let state: PaymentState;
    if (paid >= p.amount) state = "paid";
    else if (p.date < todayIso) state = "overdue";
    else if (!nextFound) {
      state = paid > 0 ? "partial" : "next";
      nextFound = true;
    } else state = "later";
    return { date: p.date, amount: p.amount, paid, state };
  });
}

function daysUntil(iso: string) {
  const ms = Date.parse(`${iso}T00:00:00`) - new Date().setHours(0, 0, 0, 0);
  return Math.round(ms / 86_400_000);
}

function plural(n: number, one: string, few: string, many: string) {
  const m10 = n % 10;
  const m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return one;
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few;
  return many;
}

function useCopy() {
  const [copied, setCopied] = useState(false);
  async function copy(value: string) {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      /* буфер обмена недоступен — значение всё равно можно выделить мышкой */
    }
  }
  return { copied, copy };
}

// Коды (БИН, ИИК, БИК…) — моноширинным шрифтом, чтобы их было легко сверить по цифрам
function CopyRow({ label, value, code }: { label: string; value: string; code?: boolean }) {
  const { copied, copy } = useCopy();
  return (
    <div className="req-row">
      <div className="req-label">{label}</div>
      <div className={code ? "req-value mono" : "req-value"}>{value}</div>
      <button type="button" className="copy-btn" onClick={() => copy(value)} aria-label={`Скопировать: ${label}`}>
        {copied ? "Скопировано" : "Копировать"}
      </button>
    </div>
  );
}

function Requisites({ p, amount }: { p: PaymentInfo; amount: number }) {
  const all = [
    `Получатель: ${p.recipient}`,
    `БИН: ${p.bin}`,
    `Банк: ${p.bank}`,
    `ИИК: ${p.iik}`,
    `БИК: ${p.bik}`,
    `КБе: ${p.kbe}`,
    `КНП: ${p.knp}`,
    `Сумма: ${formatKzt(amount)}`,
    `Назначение: ${p.purpose}`,
  ].join("\n");
  const { copied, copy } = useCopy();
  return (
    <div className="requisites">
      <div className="req-head">
        <h4>Реквизиты для перевода</h4>
        {p.demo && <span className="demo-tag">демо-реквизиты</span>}
        <button type="button" className="btn btn-ghost small-btn req-copy-all" onClick={() => copy(all)}>
          {copied ? "Скопировано ✓" : "Скопировать всё для бухгалтера"}
        </button>
      </div>
      <CopyRow label="Получатель" value={p.recipient} />
      <CopyRow label="БИН" value={p.bin} code />
      <CopyRow label="Банк" value={p.bank} />
      <CopyRow label="ИИК (счёт)" value={p.iik} code />
      <CopyRow label="БИК" value={p.bik} code />
      <CopyRow label="КБе / КНП" value={`${p.kbe} / ${p.knp}`} code />
      <CopyRow label="Назначение платежа" value={p.purpose} />
      <p className="muted small">
        Номер договора в назначении обязателен — по нему платёж зачтётся автоматически, обычно в течение одного
        рабочего дня.
      </p>
    </div>
  );
}

export default function HowToPay({ deal }: { deal: Deal }) {
  const p = deal.payment;
  if (!p || deal.status === "repaid") {
    return deal.status === "repaid" ? (
      <div className="pay-done">✓ Рассрочка погашена полностью. Спасибо! Новый сезон — новая заявка в пару кликов.</div>
    ) : null;
  }

  const items = plan(deal);
  const upcoming = items.find((i) => i.state === "overdue") ?? items.find((i) => i.state === "next" || i.state === "partial");
  const dueNow = upcoming ? upcoming.amount - upcoming.paid : 0;
  const left = deal.farmer_total - deal.paid_amount;
  const paidPct = deal.farmer_total ? (deal.paid_amount / deal.farmer_total) * 100 : 0;
  const days = upcoming ? daysUntil(upcoming.date) : 0;
  const beforeHarvest = ["contracted", "supplier_paid"].includes(deal.status);

  return (
    <div className="how-to-pay">
      <div className="pay-hero">
        {upcoming && (
          <div className={upcoming.state === "overdue" ? "next-payment overdue" : "next-payment"}>
            <div className="np-label">{upcoming.state === "overdue" ? "Просроченный платёж" : "Ближайший платёж"}</div>
            <div className="np-amount">{formatKzt(dueNow)}</div>
            <div className="np-date">
              до {formatDate(upcoming.date)}
              {upcoming.state === "overdue"
                ? " · срок прошёл"
                : ` · через ${days} ${plural(days, "день", "дня", "дней")}`}
            </div>
          </div>
        )}
        <div className="pay-progress">
          <div className="pp-row">
            <span>Оплачено</span>
            <b>
              {formatKzt(deal.paid_amount)} из {formatKzt(deal.farmer_total)}
            </b>
          </div>
          <div className="meter">
            <div className="meter-fill" style={{ width: `${paidPct}%` }} />
          </div>
          <div className="pp-row muted small">
            <span>Осталось {formatKzt(left)}</span>
            <span>
              {items.filter((i) => i.state === "paid").length} из {items.length} платежей
            </span>
          </div>
        </div>
      </div>

      <ol className="pay-schedule">
        {items.map((i, n) => (
          <li key={i.date} className={`ps-${i.state}`}>
            <span className="ps-dot" aria-hidden />
            <div className="ps-main">
              <b>{n + 1}-й платёж</b> · {formatDate(i.date)}
              <div className="muted small">
                {STATE_LABEL[i.state]}
                {i.state === "partial" && ` · внесено ${formatKzt(i.paid)}`}
              </div>
            </div>
            <div className="num ps-amount">{formatKzt(i.amount)}</div>
          </li>
        ))}
      </ol>

      {beforeHarvest && (
        <p className="notice">
          Сейчас платить ничего не нужно: первый платёж — после уборки урожая. Реквизиты ниже пригодятся осенью; их же
          можно передать бухгалтеру заранее.
        </p>
      )}

      <div className="pay-ways">
        <div className="pay-way">
          <div className="pw-icon" aria-hidden>
            📱
          </div>
          <h4>Из приложения банка</h4>
          <p>
            Перевод юрлицу по реквизитам из интернет-банка хозяйства — подойдёт счёт в любом банке Казахстана. Комиссия
            — по тарифам вашего банка.
          </p>
        </div>
        <div className="pay-way">
          <div className="pw-icon" aria-hidden>
            🧾
          </div>
          <h4>Через бухгалтерию</h4>
          <p>Платёжное поручение по реквизитам ниже. Обязательно укажите номер договора в назначении платежа.</p>
        </div>
        <div className="pay-way">
          <div className="pw-icon" aria-hidden>
            ⏩
          </div>
          <h4>Раньше срока или частями</h4>
          <p>
            Можно платить частями и досрочно — сразу после продажи урожая. Сумма к возврату фиксирована в договоре и не
            растёт.
          </p>
        </div>
      </div>

      <Requisites p={p} amount={dueNow || left} />

      <details className="pay-faq">
        <summary>Что делать, если урожай подвёл?</summary>
        <p>
          Урожай застрахован: если погибло больше {formatPct(p.insurance_deductible)} урожая, страховая выплата
          направляется в счёт рассрочки. Если денег всё равно не хватает, остаток переносится на следующий сезон с
          доплатой {formatPct(p.restructure_fee)} — без штрафов и без изъятия техники. Сообщите нам до первого платежа:{" "}
          <a href={`mailto:${p.support_email}`}>{p.support_email}</a>.
        </p>
      </details>
      <details className="pay-faq">
        <summary>Из чего складывается сумма к возврату?</summary>
        <p>
          Стоимость товара по розничной цене поставщика ({formatKzt(deal.goods_amount)}) плюс наценка за рассрочку{" "}
          {formatPct(p.fee_rate, 1)} — итого {formatKzt(deal.farmer_total)}. Других комиссий и процентов нет; наценка
          зависит от класса риска поля и указана в договоре.
        </p>
      </details>
      <details className="pay-faq">
        <summary>Как понять, что платёж дошёл?</summary>
        <p>
          На этой странице обновится «Оплачено», а платёж в графике отметится как оплаченный — обычно на следующий
          рабочий день. Если прошло больше трёх дней, напишите на{" "}
          <a href={`mailto:${p.support_email}`}>{p.support_email}</a> и приложите платёжное поручение.
        </p>
      </details>
    </div>
  );
}
