// Чек-лист проверки хозяйства: реестр, возраст, налоги, аресты, суды, господдержка.
// Статус дублируется значком и словом — не только цветом.
import type { Check } from "../types";

const ICON: Record<Check["status"], string> = { ok: "✓", warn: "!", fail: "✕", info: "i" };

export default function ChecksList({ checks }: { checks: Check[] }) {
  if (checks.length === 0) return null;
  return (
    <ul className="checks">
      {checks.map((c) => (
        <li key={c.label} className={`check check-${c.status}`}>
          <span className="check-icon" aria-hidden>
            {ICON[c.status]}
          </span>
          <span className="check-label">{c.label}</span>
          <span className="check-detail">{c.detail}</span>
        </li>
      ))}
    </ul>
  );
}
