import { useEffect, useState } from 'react';
import WalletStatus from './components/WalletStatus';
import { migrateStorage } from './services/storage';
import BoostsPage from './features/BoostsPage';
import CalculatePage from './features/CalculatePage';
import MasterpiecePage from './features/MasterpiecePage';
import ProfitabilityPage from './features/ProfitabilityPage';
import ChainsPage from './features/ChainsPage';

const tabs = [
  { id: 'boosts', label: 'Boosts' },
  { id: 'calculate', label: 'Calculate' },
  { id: 'masterpiece', label: 'Masterpiece' },
  { id: 'profitability', label: 'Profitability' },
  { id: 'chains', label: 'Chains' },
] as const;

export default function App() {
  const [active, setActive] = useState<(typeof tabs)[number]['id']>('boosts');

  useEffect(() => {
    migrateStorage();
  }, []);

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="app-header-inner">
          <div className="app-title">Craftworld Tools</div>
          <div className="nav-bar">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                type="button"
                className={`nav-item ${active === tab.id ? 'active' : ''}`}
                onClick={() => setActive(tab.id)}
              >
                {tab.label}
              </button>
            ))}
          </div>
        </div>
      </header>

      <main className="container">
        <div className="card">
          <WalletStatus />
        </div>
        {active === 'boosts' && <BoostsPage />}
        {active === 'calculate' && <CalculatePage />}
        {active === 'masterpiece' && <MasterpiecePage />}
        {active === 'profitability' && <ProfitabilityPage />}
        {active === 'chains' && <ChainsPage />}
      </main>

      <nav className="bottom-nav">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            className={active === tab.id ? '' : 'secondary'}
            onClick={() => setActive(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </nav>
    </div>
  );
}
