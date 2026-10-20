import { Link } from "react-router-dom";
import { getMyApplications } from "../lib/storage";
import { formatDate } from "../lib/format";

const STEPS = [
  {
    n: "01",
    title: "Указываете БИН",
    text: "Проверяем хозяйство по реестру юрлиц: существует, действует, работает больше года.",
  },
  {
    n: "02",
    title: "Обводите поле на карте",
    text: "Пара кликов по спутниковому снимку. Площадь считается сразу, справки о собственности не нужны.",
  },
  {
    n: "03",
    title: "Получаете решение",
    text: "Анализируем 7 сезонов спутниковых снимков поля и выдаём лимит на семена и удобрения до осени.",
  },
];

export default function Landing() {
  const mine = getMyApplications();

  return (
    <>
      <section className="hero">
        <div className="hero-inner">
          <p className="eyebrow">Рассрочка для фермеров Казахстана</p>
          <h1>
            Семена и удобрения сейчас.
            <br />
            Оплата — после урожая.
          </h1>
          <p className="lead">
            Вместо залога техники и недель в банке — история вашего поля со спутника. Решение за несколько минут.
          </p>
          <div className="hero-actions">
            <Link to="/apply" className="btn btn-primary">
              Подать заявку
            </Link>
            <a href="#how" className="btn btn-ghost">
              Как это работает
            </a>
          </div>
        </div>
      </section>

      <section id="how" className="container section">
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

      <section className="container section">
        <h2>Как мы оцениваем поле</h2>
        <div className="explain">
          <p>
            Для каждого сезона считаем <b>NDVI</b> — индекс, который показывает, насколько густая и живая растительность
            на поле. Облака отфильтровываем, иначе они дают ложный «неурожай». Из семи сезонов складывается{" "}
            <b>индекс стабильности</b> от 0 до 100:
          </p>
          <ul>
            <li>
              <b>50%</b> — средний уровень NDVI: хорошо ли поле родит в принципе;
            </li>
            <li>
              <b>30%</b> — стабильность: не скачет ли урожай от года к году;
            </li>
            <li>
              <b>20%</b> — тренд: поле улучшается или истощается.
            </li>
          </ul>
          <div className="classes">
            <div>
              <span className="class-badge class-A">A</span> 75+ — одобряем полный лимит
            </div>
            <div>
              <span className="class-badge class-B">B</span> 50–74 — одобряем 60% лимита
            </div>
            <div>
              <span className="class-badge class-C">C</span> до 50 — заявку смотрит аналитик
            </div>
          </div>
        </div>
      </section>

      {mine.length > 0 && (
        <section className="container section">
          <h2>Мои заявки</h2>
          <ul className="my-apps">
            {mine.map((a) => (
              <li key={a.id}>
                <Link to={`/applications/${a.id}`}>{a.farm}</Link>
                <span className="muted"> · {formatDate(a.createdAt)}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}
