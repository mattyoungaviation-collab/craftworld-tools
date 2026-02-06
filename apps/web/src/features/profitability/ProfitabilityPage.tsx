import { useEffect, useMemo, useState } from 'react';
import {
  computeBestSetupsCsv,
  getFactoryDisplayOrder,
  parseFactoriesFromCsv,
  type PriceMap,
} from '@craftworld/shared';
import factoriesCsv from '@craftworld/data/factories.csv?raw';
import { fetchExchangePricesCoin } from '../../services/pricing';

export default function ProfitabilityPage() {
  const factories = useMemo(() => parseFactoriesFromCsv(factoriesCsv), []);
  const tokens = useMemo(() => getFactoryDisplayOrder(factories), [factories]);
  const [prices, setPrices] = useState<PriceMap>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let mounted = true;
    fetchExchangePricesCoin()
      .then((data) => {
        if (mounted) {
          setPrices(data);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (mounted) {
          setError(String(err));
          setLoading(false);
        }
      });
    return () => {
      mounted = false;
    };
  }, []);

  const { results } = useMemo(() => {
    if (!Object.keys(prices).length) {
      return { results: [] as { token: string; profit_coin_per_hour: number; profit_coin_per_craft: number; level: number }[] };
    }
    return computeBestSetupsCsv(factories, prices, 1, 0, 100, 15);
  }, [factories, prices]);

  return (
    <section className="card">
      <h2>Profitability</h2>
      {loading && <p className="muted">Loading prices...</p>}
      {error && <p className="status">{error}</p>}
      <div className="table-wrapper">
        <table className="table">
          <thead>
            <tr>
              <th>Token</th>
              <th>Max Level</th>
              <th>Profit / craft (COIN)</th>
              <th>Profit / hour (COIN)</th>
            </tr>
          </thead>
          <tbody>
            {results.map((row) => (
              <tr key={row.token}>
                <td>{row.token}</td>
                <td>{row.level}</td>
                <td>{row.profit_coin_per_craft.toFixed(6)}</td>
                <td>{row.profit_coin_per_hour.toFixed(6)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!results.length && !loading && <p className="muted">No data available.</p>}
      <p className="muted">Tokens evaluated: {tokens.length}</p>
    </section>
  );
}
