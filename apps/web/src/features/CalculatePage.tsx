import { useMemo, useState } from 'react';
import { computeFactoryResultCsv } from '@shared/factories';
import { FACTORIES, FACTORY_ORDER } from '../services/factoriesData';
import { fetchPrices } from '../services/pricing';

export default function CalculatePage() {
  const [token, setToken] = useState(FACTORY_ORDER[0] || 'MUD');
  const [level, setLevel] = useState(1);
  const [targetLevel, setTargetLevel] = useState<number | null>(null);
  const [count, setCount] = useState(1);
  const [yieldPct, setYieldPct] = useState(100);
  const [speedFactor, setSpeedFactor] = useState(1);
  const [workers, setWorkers] = useState(0);
  const [prices, setPrices] = useState<Record<string, number>>({});
  const [status, setStatus] = useState('');

  const levels = useMemo(() => {
    const data = FACTORIES[token] || {};
    return Object.keys(data)
      .map((lvl) => Number(lvl))
      .filter((lvl) => Number.isFinite(lvl))
      .sort((a, b) => a - b);
  }, [token]);

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

  const result = useMemo(() => {
    try {
      if (!prices || Object.keys(prices).length === 0) return null;
      return computeFactoryResultCsv(
        FACTORIES,
        prices,
        token,
        level,
        targetLevel,
        count,
        yieldPct,
        speedFactor,
        workers,
      );
    } catch {
      return null;
    }
  }, [token, level, targetLevel, count, yieldPct, speedFactor, workers, prices]);

  return (
    <section className="card">
      <h2>Calculate</h2>
      <p className="muted">CSV-driven factory calculator (same formulas as legacy app).</p>
      <div className="notice">{status || 'Load prices to compute results.'}</div>
      <div className="grid grid-2">
        <label>
          Token
          <select value={token} onChange={(e) => setToken(e.target.value)}>
            {FACTORY_ORDER.map((tok) => (
              <option key={tok} value={tok}>{tok}</option>
            ))}
          </select>
        </label>
        <label>
          Level
          <select value={level} onChange={(e) => setLevel(Number(e.target.value))}>
            {levels.map((lvl) => (
              <option key={lvl} value={lvl}>L{lvl}</option>
            ))}
          </select>
        </label>
        <label>
          Target Level (optional)
          <select
            value={targetLevel ?? ''}
            onChange={(e) => setTargetLevel(e.target.value ? Number(e.target.value) : null)}
          >
            <option value="">None</option>
            {levels.map((lvl) => (
              <option key={lvl} value={lvl}>L{lvl}</option>
            ))}
          </select>
        </label>
        <label>
          Factory Count
          <input type="number" value={count} onChange={(e) => setCount(Number(e.target.value))} />
        </label>
        <label>
          Yield %
          <input type="number" value={yieldPct} onChange={(e) => setYieldPct(Number(e.target.value))} />
        </label>
        <label>
          Speed Factor
          <input type="number" value={speedFactor} onChange={(e) => setSpeedFactor(Number(e.target.value))} />
        </label>
        <label>
          Workers
          <input type="number" value={workers} onChange={(e) => setWorkers(Number(e.target.value))} />
        </label>
      </div>
      <div style={{ marginTop: 12, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <button type="button" onClick={loadPrices}>Load Prices</button>
      </div>
      {result && (
        <div className="card" style={{ marginTop: 16 }}>
          <h3>Result</h3>
          <p className="muted">Profit per hour: {result.profit_coin_per_hour.toFixed(6)} COIN</p>
          <table className="table">
            <tbody>
              <tr>
                <td>Output</td>
                <td>{result.out_amount.toFixed(4)} {result.out_token}</td>
              </tr>
              <tr>
                <td>Duration (min)</td>
                <td>{result.duration_min.toFixed(2)}</td>
              </tr>
              <tr>
                <td>Crafts / hour</td>
                <td>{result.crafts_per_hour.toFixed(4)}</td>
              </tr>
              <tr>
                <td>Profit / craft (COIN)</td>
                <td>{result.profit_coin_per_craft.toFixed(6)}</td>
              </tr>
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
