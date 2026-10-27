import { Link } from "react-router-dom";
import { getMyApplications } from "../lib/storage";
import { formatDate } from "../lib/format";

const STEPS = [
  {
    n: "01",
    title: "Указываете БИН",
    text: "Проверяем хозяйство по госбазам: действует, работает больше года, нет налоговых долгов и арестов.",
  },
  {
    n: "02",
    title: "Обводите поле на карте",
    text: "Находите своё поле по названию села и обводите кликами — или загружаете файл KML из Google Earth.",
  },
  {
    n: "03",
    title: "Получаете решение",
    text: "Смотрим 7 сезонов спутниковых снимков поля и за минуту выдаём лимит на семена и удобрения до осени.",
  },
];

const TERMS = [
  { value: "0 ₸", label: "первоначальный взнос", note: "товар получаете весной, платите после уборки" },
  { value: "6–10 %", label: "наценка за весь срок", note: "класс A — 6 %, класс B — 10 %; без процентов и комиссий" },
  { value: "2 платежа", label: "15 октября и 15 ноября", note: "можно раньше и частями — сумма не растёт" },
  { value: "до 20 млн ₸", label: "лимит на одну заявку", note: "60 000 ₸ на гектар, зависит от истории поля" },
];

const PAY_STEPS = [
  {
    title: "Весна: товар без денег",
    text: "После одобрения мы сами оплачиваем поставщикам, и они отгружают семена и удобрения перед севом.",
  },
  {
    title: "Лето: ничего не платите",
    text: "Всходы видим со спутника — проверок на поле и отчётов не нужно. Урожай застрахован.",
  },
  {
    title: "Осень: два платежа",
    text: "После продажи урожая переводите деньги по реквизитам с номером договора — из приложения любого банка Казахстана.",
  },
];

const FAQ = [
  {
    q: "Как оплачивать рассрочку?",
    a: "Обычным переводом юрлицу из интернет-банка хозяйства или платёжным поручением через бухгалтерию. Реквизиты спецсчёта и номер договора появятся на странице вашей заявки сразу после одобрения — с кнопками «Копировать». Подойдёт счёт в любом банке Казахстана.",
  },
  {
    q: "Какой банк выдаёт деньги?",
    a: "Деньги поставщикам платит банк-партнёр из кредитной линии платформы. Вам не нужно открывать счёт в этом банке и ходить в отделение: договор подписывается с Harvest Pay, а платить можно с любого вашего счёта.",
  },
  {
    q: "Что если урожай не удался?",
    a: "Урожай страхуется: при гибели больше 30 % урожая страховая выплата идёт в счёт рассрочки. Если денег всё равно не хватает, остаток переносится на следующий сезон с доплатой 8 % — без штрафов и без изъятия техники.",
  },
  {
    q: "Можно погасить раньше срока?",
    a: "Да, в любой момент и любыми частями. Сумма к возврату фиксирована в договоре, поэтому досрочный платёж ничего не стоит.",
  },
  {
    q: "Какие документы нужны?",
    a: "Для заявки — только БИН и границы поля. Кадастровый номер участка ускорит проверку. Договор подписывается после одобрения заявки.",
  },
  {
    q: "Почему без залога?",
    a: "Мы оцениваем не технику, а само поле: как оно давало урожай последние 7 лет по снимкам Sentinel-2. Стабильное поле — лучшая гарантия, чем старый трактор.",
  },
];

// Макет результата в первом экране: показывает, что фермер получит, без лишних слов
function HeroMock() {
  const bars = [0.75, 0.66, 0.72, 0.43, 0.79, 0.74, 0.64];
  return (
    <div className="hero-mock" aria-hidden>
      <div className="hm-head">
        <span className="class-badge class-A">A</span>
        <div>
          <div className="hm-title">Низкий риск · 82 / 100</div>
          <div className="hm-sub">КХ «Нур Егін» · пшеница · 94 га</div>
        </div>
      </div>
      <div className="hm-bars">
        {bars.map((v, i) => (
          <div key={i} className="hm-bar-col">
            <div className={v < 0.5 ? "hm-bar weak" : "hm-bar"} style={{ height: `${v * 100}%` }} />
            <span>{2020 + i}</span>
          </div>
        ))}
      </div>
      <div className="hm-kpis">
        <div>
          <span>Одобрено</span>
          <b>5 600 000 ₸</b>
        </div>
        <div>
          <span>Оплата</span>
          <b>15 окт · 15 ноя</b>
        </div>
      </div>
    </div>
  );
}

export default function Landing() {
  const mine = getMyApplications();

  return (
    <>
      <section className="hero">
        <div className="hero-inner hero-grid">
          <div>
            <p className="eyebrow">Рассрочка для фермеров Казахстана</p>
            <h1>
              Семена и удобрения сейчас.
              <br />
              <span className="accent">Оплата — после урожая.</span>
            </h1>
            <p className="lead">
              Вместо залога техники и недель в банке — история вашего поля со спутника. Решение за минуту, без поездок
              в отделение.
            </p>
            <div className="hero-actions">
              <Link to="/apply" className="btn btn-primary btn-lg">
                Подать заявку
              </Link>
              <a href="#terms" className="btn btn-ghost btn-lg">
                Условия и оплата
              </a>
            </div>
            <ul className="hero-facts">
              <li>
                <b>7 сезонов</b> снимков поля
              </li>
              <li>
                <b>0 ₸</b> залога
              </li>
              <li>
                <b>~1 мин</b> на решение
              </li>
            </ul>
          </div>
          <HeroMock />
        </div>
      </section>

      {mine.length > 0 && (
        <section className="container section">
          <div className="my-apps-card">
            <h2>Мои заявки</h2>
            <ul className="my-apps">
              {mine.map((a) => (
                <li key={a.id}>
                  <Link to={`/applications/${a.id}`}>{a.farm}</Link>
                  <span className="muted"> · {formatDate(a.createdAt)}</span>
                </li>
              ))}
            </ul>
          </div>
        </section>
      )}

      <section id="how" className="container section">
        <p className="section-eyebrow">Как это работает</p>
        <h2>Три шага до решения</h2>
        <div className="steps">
          {STEPS.map((s) => (
            <article key={s.n} className="step">
              <span className="step-n">{s.n}</span>
              <h3>{s.title}</h3>
              <p>{s.text}</p>
            </article>
          ))}
        </div>
      </section>

      <section id="terms" className="container section">
        <p className="section-eyebrow">Условия</p>
        <h2>Сколько стоит и когда платить</h2>
        <div className="terms">
          {TERMS.map((t) => (
            <div key={t.label} className="term">
              <div className="term-value">{t.value}</div>
              <div className="term-label">{t.label}</div>
              <p className="muted small">{t.note}</p>
            </div>
          ))}
        </div>
        <div className="season-path">
          {PAY_STEPS.map((s, i) => (
            <div key={s.title} className="sp-step">
              <span className="sp-n">{i + 1}</span>
              <h3>{s.title}</h3>
              <p>{s.text}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="container section">
        <p className="section-eyebrow">Скоринг</p>
        <h2>Как мы оцениваем поле</h2>
        <div className="explain">
          <p>
            Для каждого сезона считаем <b>NDVI</b> — индекс, который показывает, насколько густая и живая растительность
            на поле. Облака отфильтровываем, иначе они дают ложный «неурожай». Из семи сезонов складывается{" "}
            <b>индекс стабильности</b> от 0 до 100:
          </p>
          <div className="weights">
            <div>
              <b>50%</b>
              <span>средний уровень NDVI — хорошо ли поле родит в принципе</span>
            </div>
            <div>
              <b>30%</b>
              <span>стабильность — не скачет ли урожай от года к году</span>
            </div>
            <div>
              <b>20%</b>
              <span>тренд — поле улучшается или истощается</span>
            </div>
          </div>
          <div className="classes">
            <div>
              <span className="class-badge class-A">A</span> 75+ — одобряем полный лимит, наценка 6 %
            </div>
            <div>
              <span className="class-badge class-B">B</span> 50–74 — одобряем 60% лимита, наценка 10 %
            </div>
            <div>
              <span className="class-badge class-C">C</span> до 50 — заявку смотрит кредитный аналитик
            </div>
          </div>
        </div>
      </section>

      <section id="faq" className="container section">
        <p className="section-eyebrow">Вопросы</p>
        <h2>Частые вопросы</h2>
        <div className="faq">
          {FAQ.map((f) => (
            <details key={f.q}>
              <summary>{f.q}</summary>
              <p>{f.a}</p>
            </details>
          ))}
        </div>
      </section>

      <section className="container section">
        <div className="cta">
          <div>
            <h2>Узнайте свой лимит за минуту</h2>
            <p>Нужны только БИН хозяйства и границы поля. Заявка ни к чему не обязывает.</p>
          </div>
          <Link to="/apply" className="btn btn-primary btn-lg">
            Подать заявку
          </Link>
        </div>
      </section>
    </>
  );
}
