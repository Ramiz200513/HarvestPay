import { Link, NavLink, Route, Routes } from "react-router-dom";
import Analyst from "./pages/Analyst";
import ApplicationPage from "./pages/ApplicationPage";
import Apply from "./pages/Apply";
import Landing from "./pages/Landing";

export default function App() {
  return (
    <>
      <header className="topbar">
        <div className="container topbar-inner">
          <Link to="/" className="logo">
            <img src="/favicon.svg" alt="" width={28} height={28} />
            Harvest Pay
          </Link>
          <nav>
            <NavLink to="/apply">Подать заявку</NavLink>
            <NavLink to="/analyst">Аналитику</NavLink>
          </nav>
        </div>
      </header>

      <main>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/apply" element={<Apply />} />
          <Route path="/applications/:id" element={<ApplicationPage />} />
          <Route path="/analyst" element={<Analyst />} />
          <Route path="*" element={<div className="container page">Страница не найдена. <Link to="/">На главную</Link></div>} />
        </Routes>
      </main>

      <footer className="footer">
        <div className="container">Harvest Pay · учебный проект · спутниковые данные: Copernicus Sentinel-1/2 через Google Earth Engine</div>
      </footer>
    </>
  );
}
