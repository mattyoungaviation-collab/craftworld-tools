import { useMemo, useState } from 'react';
import { buildChainReport, CRAFTING_CHAINS } from '@shared/crafting';
import { FACTORIES } from '../services/factoriesData';
import { fetchPrices } from '../services/pricing';
import { getActiveWallet, getBoostStorageKey } from '../services/storage';

const chainList = Object.keys(CRAFTING_CHAINS);

export default function ChainsPage() {
  const [selectedChains, setSelectedChains] = useState<string[]>(chainList);
  const [startAmount, setStartAmount] = useState(1);
  const [prices, setPrices] = useState<Record<string, number>>({});
  const [status, setStatus] = useState('');

  const modifiers = useMemo(() => {
    const wallet = getActiveWallet();
    if (!wallet) return { masteryLevelsBySymbol: {}, workshopLevelsByFactoryOrTier: {}, globalSpeedMultiplier: 1.0 };
    const stored = localStorage.getItem(getBoostStorageKey(wallet));
    if (!stored) return { masteryLevelsBySymbol: {}, workshopLevelsByFactoryOrTier: {}, globalSpeedMultiplier: 1.0 };
    try {
      const parsed = JSON.parse(stored);
      return {
        masteryLevelsBySymbol: parsed.masteryLevels || parsed.mastery || {},
        workshopLevelsByFactoryOrTier: parsed.workshopLevels || parsed.workshop || {},
        globalSpeedMultiplier: 1.0,
      };
    } catch {
      return { masteryLevelsBySymbol: {}, workshopLevelsByFactoryOrTier: {}, globalSpeedMultiplier: 1.0 };
    }
  }, []);

  async function loadPrices() {
    try {
      setStatus('Loading prices...');
      const data = await fetchPrices();
      setPrices(data);
      setStatus('Prices loaded.');
    } catch (err: any) {
      setStatus(String(err?.message || err));
    }
  }

  const reports = useMemo(() => {
    if (!prices || Object.keys(prices).length === 0) return [];
    return selectedChains.map((name) =>
      buildChainReport(
        FACTORIES,
        name,
        CRAFTING_CHAINS[name],
        prices,
        modifiers,
        startAmount,
      ),
    );
  }, [selectedChains, prices, startAmount, modifiers]);

  return (
    <section className="card">
      <h2>Crafting Chains</h2>
      <p className="muted">Analyze dependency chains using live prices.</p>
      <div className="notice">{status || 'Load prices to calculate chains.'}</div>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <button type="button" onClick={loadPrices}>Load Prices</button>
        <label>
          Start Amount
          <input type="number" value={startAmount} onChange={(e) => setStartAmount(Number(e.target.value))} />
        </label>
      </div>
      <div style={{ marginTop: 12, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        {chainList.map((chain) => (
          <label key={chain} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <input
              type="checkbox"
              checked={selectedChains.includes(chain)}
              onChange={(e) => {
                setSelectedChains((prev) =>
                  e.target.checked ? [...prev, chain] : prev.filter((c) => c !== chain),
                );
              }}
            />
            {chain}
          </label>
        ))}
      </div>
      {reports.map((report) => (
        <div key={report.name} className="card" style={{ marginTop: 16 }}>
          <h3>{report.name}</h3>
          {report.error ? (
            <p className="muted">{report.error}</p>
          ) : (
            <>
              <p className="muted">
                Total ROI: {(report.total_roi || 0).toFixed(4)} • Total Profit: {(report.total_profit || 0).toFixed(6)}
              </p>
              <table className="table">
                <thead>
                  <tr>
                    <th>From</th>
                    <th>To</th>
                    <th>Profit</th>
                    <th>ROI</th>
                  </tr>
                </thead>
                <tbody>
                  {report.stages.map((stage, index) => (
                    <tr key={`${stage.to}-${index}`}>
                      <td>{stage.from}</td>
                      <td>{stage.to}</td>
                      <td>{stage.stage_profit.toFixed(6)}</td>
                      <td>{stage.stage_roi.toFixed(4)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </div>
      ))}
    </section>
  );
}
