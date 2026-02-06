import { useMemo, useState } from 'react';
import {
  computeFactoryResultCsv,
  getFactoryDisplayOrder,
  parseFactoriesFromCsv,
  type PriceMap,
} from '@craftworld/shared';
import factoriesCsv from '@craftworld/data/factories.csv?raw';

const DEFAULT_PRICES: PriceMap = { COIN: 1 };

export default function CalculatePage() {
  const factories = useMemo(() => parseFactoriesFromCsv(factoriesCsv), []);
  const tokens = useMemo(() => getFactoryDisplayOrder(factories), [factories]);
  const [token, setToken] = useState(tokens[0] || 'MUD');
  const [level, setLevel] = useState(1);
  const [count, setCount] = useState(1);
  const [yieldPct, setYieldPct] = useState(100);
  const [speedFactor, setSpeedFactor] = useState(1);
  const [workers, setWorkers] = useState(0);

  const result = useMemo(() => {
    try {
      return computeFactoryResultCsv(
        factories,
        DEFAULT_PRICES,
        token,
        level,
        null,
        count,
        yieldPct,
        speedFactor,
        workers,
      );
    } catch (_err) {
      return null;
    }
  }, [factories, token, level, count, yieldPct, speedFactor, workers]);

  const levels = Object.keys(factories[token] || {}).map((value) => Number(value));

  return (
    <section className="card">
      <h2>Calculate</h2>
      <div className="form-grid">
        <label>
          Token
          <select value={token} onChange={(event) => setToken(event.target.value)}>
            {tokens.map((tok) => (
              <option key={tok} value={tok}>
                {tok}
              </option>
            ))}
          </select>
        </label>
        <label>
          Level
          <select value={level} onChange={(event) => setLevel(Number(event.target.value))}>
            {levels.map((lvl) => (
              <option key={lvl} value={lvl}>
                {lvl}
              </option>
            ))}
          </select>
        </label>
        <label>
          Count
          <input type="number" value={count} onChange={(event) => setCount(Number(event.target.value))} />
        </label>
        <label>
          Yield %
          <input type="number" value={yieldPct} onChange={(event) => setYieldPct(Number(event.target.value))} />
        </label>
        <label>
          Speed factor
          <input type="number" value={speedFactor} onChange={(event) => setSpeedFactor(Number(event.target.value))} />
        </label>
        <label>
          Workers
          <input type="number" value={workers} onChange={(event) => setWorkers(Number(event.target.value))} />
        </label>
      </div>

      {result ? (
        <div className="card" style={{ marginTop: '16px' }}>
          <h3>Output</h3>
          <div className="table-wrapper">
            <table className="table">
              <tbody>
                <tr>
                  <th>Output</th>
                  <td>{result.out_amount} {result.out_token}</td>
                </tr>
                <tr>
                  <th>Crafts / hour</th>
                  <td>{result.crafts_per_hour.toFixed(4)}</td>
                </tr>
                <tr>
                  <th>Profit / craft</th>
                  <td>{result.profit_coin_per_craft.toFixed(6)} COIN</td>
                </tr>
                <tr>
                  <th>Profit / hour</th>
                  <td>{result.profit_coin_per_hour.toFixed(6)} COIN</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <p className="muted">Select a valid token and level.</p>
      )}
    </section>
  );
}
