import { useState } from 'react';
import { computeBestSetupsCsv } from '@shared/factories';
import { FACTORIES } from '../services/factoriesData';
import { fetchPrices } from '../services/pricing';

export default function ProfitabilityPage() {
  const [speedFactor, setSpeedFactor] = useState(1);
  const [workers, setWorkers] = useState(0);
  const [yieldPct, setYieldPct] = useState(100);
  const [topN, setTopN] = useState(15);
  const [prices, setPrices] = useState<Record<string, number>>({});
  const [status, setStatus] = useState('');
  const [results, setResults] = useState<ReturnType<typeof computeBestSetupsCsv> | null>(null);

  async function load() {
    try {
      setStatus('Loading prices...');
      const data = await fetchPrices();
      setPrices(data);
      const computed = computeBestSetupsCsv(FACTORIES, data, speedFactor, workers, yieldPct, topN);
      setResults(computed);
      setStatus('Profitability computed.');
    } catch (err: any) {
      setStatus(String(err?.message || err));
    }
  }

  return (
    <section className="card">
      <h2>Profitability</h2>
      <p className="muted">Ranks factory outputs by profit per hour.</p>
      <div className="notice">{status || 'Load prices to calculate profitability.'}</div>
      <div className="grid grid-2">
        <label>
          Speed Factor
          <input type="number" value={speedFactor} onChange={(e) => setSpeedFactor(Number(e.target.value))} />
        </label>
        <label>
          Workers
          <input type="number" value={workers} onChange={(e) => setWorkers(Number(e.target.value))} />
        </label>
        <label>
          Yield %
          <input type="number" value={yieldPct} onChange={(e) => setYieldPct(Number(e.target.value))} />
        </label>
        <label>
          Top N
          <input type="number" value={topN} onChange={(e) => setTopN(Number(e.target.value))} />
        </label>
      </div>
      <div style={{ marginTop: 12 }}>
        <button type="button" onClick={load}>Compute</button>
      </div>
      {results && (
        <div className="card" style={{ marginTop: 16 }}>
          <p className="muted">
            Combined speed: {results.combined_speed.toFixed(2)} • Worker factor: {results.worker_factor.toFixed(2)}
          </p>
          <table className="table">
            <thead>
              <tr>
                <th>Token</th>
                <th>Level</th>
                <th>Profit / craft</th>
                <th>Profit / hour</th>
              </tr>
            </thead>
            <tbody>
              {results.results.map((row) => (
                <tr key={row.token}>
                  <td>{row.token}</td>
                  <td>L{row.level}</td>
                  <td>{row.profit_coin_per_craft.toFixed(6)}</td>
                  <td>{row.profit_coin_per_hour.toFixed(6)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {prices._COIN_USD ? (
        <p className="muted">COIN USD: {Number(prices._COIN_USD).toFixed(4)}</p>
      ) : null}
    </section>
  );
}
