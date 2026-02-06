import { NavLink, Route, Routes } from 'react-router-dom';
import { useEffect } from 'react';
import BoostsPage from './features/boosts/BoostsPage';
import CalculatePage from './features/calculate/CalculatePage';
import MasterpiecePage from './features/masterpiece/MasterpiecePage';
import ProfitabilityPage from './features/profitability/ProfitabilityPage';
import ChainsPage from './features/chains/ChainsPage';
import { migrateStorage } from './services/storage';
import WalletStatus from './components/WalletStatus';

const tabs = [
  { path: '/', label: 'Boosts', element: <BoostsPage /> },
  { path: '/calculate', label: 'Calculate', element: <CalculatePage /> },
  { path: '/masterpiece', label: 'Masterpiece', element: <MasterpiecePage /> },
  { path: '/profitability', label: 'Profitability', element: <ProfitabilityPage /> },
  { path: '/chains', label: 'Chains', element: <ChainsPage /> },
];

export default function App() {
  useEffect(() => {
    migrateStorage();
  }, []);

  return (
    <div className="app">
      <header className="app-header">
        <div>
          <h1>CraftWorld Tools.Live</h1>
          <p>Modernized tools with legacy parity.</p>
        </div>
        <WalletStatus />
      </header>

      <nav className="app-tabs">
        {tabs.map((tab) => (
          <NavLink key={tab.path} to={tab.path} end={tab.path === '/'}>
            {tab.label}
          </NavLink>
        ))}
      </nav>

      <main className="app-content">
        <Routes>
          {tabs.map((tab) => (
            <Route key={tab.path} path={tab.path} element={tab.element} />
          ))}
        </Routes>
      </main>

      <nav className="app-bottom-nav">
        {tabs.map((tab) => (
          <NavLink key={tab.path} to={tab.path} end={tab.path === '/'}>
            {tab.label}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
