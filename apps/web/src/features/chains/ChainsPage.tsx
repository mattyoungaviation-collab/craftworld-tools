import { useEffect, useMemo, useState } from 'react';
import {
  buildChainReport,
  CRAFTING_CHAINS,
  parseFactoriesFromCsv,
  type ChainReport,
} from '@craftworld/shared';
import factoriesCsv from '@craftworld/data/factories.csv?raw';
import { fetchExchangePricesCoin } from '../../services/pricing';

export default function ChainsPage() {
  const factories = useMemo(() => parseFactoriesFromCsv(factoriesCsv), []);
  const [prices, setPrices] = useState<Record<string, number>>({});
  const [reports, setReports] = useState<ChainReport[]>([]);
  const [error, setError] = useState('');

  useEffect(() => {
    fetchExchangePricesCoin()
      .then((data) => setPrices(data))
      .catch((err) => setError(String(err)));
  }, []);

  useEffect(() => {
    if (!Object.keys(prices).length) return;
    const nextReports = Object.entries(CRAFTING_CHAINS).map(([name, chain]) =>
      buildChainReport(factories, name, chain, prices),
    );
    setReports(nextReports);
  }, [prices, factories]);

  return (
    <section className="card">
      <h2>Crafting Chains</h2>
      {error && <p className="status">{error}</p>}
      {reports.map((report) => (
        <div key={report.name} className="card">
          <h3>{report.name}</h3>
          {report.error ? (
            <p className="status">{report.error}</p>
          ) : (
            <div className="table-wrapper">
              <table className="table">
                <thead>
                  <tr>
                    <th>Input</th>
                    <th>Output</th>
                    <th>Profit</th>
                    <th>ROI</th>
                  </tr>
                </thead>
                <tbody>
                  {report.stages.map((stage) => (
                    <tr key={`${stage.inputSymbol}-${stage.outputSymbol}`}>
                      <td>
                        {stage.inputAmount.toFixed(2)} {stage.inputSymbol}
                      </td>
                      <td>
                        {stage.outputAmount.toFixed(2)} {stage.outputSymbol}
                      </td>
                      <td>{stage.profit.toFixed(4)} COIN</td>
                      <td>{(stage.roi * 100).toFixed(2)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      ))}
    </section>
  );
}
