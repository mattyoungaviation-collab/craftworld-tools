import { buildChainReport } from '@craftworld/shared';
import { fetchJson } from '../../../lib/api.js';

type Price = { symbol: string; price: number };

type Params = { params: { symbol: string } };

export default async function ChainPage({ params }: Params) {
  const data = await fetchJson<{ exchangePriceList: Price[] }>('/prices');
  const prices = Object.fromEntries(data.exchangePriceList.map((item) => [item.symbol, item.price]));

  const symbol = params.symbol.toUpperCase();
  const chain = symbol === 'MUD' ? ['EARTH', 'MUD', 'CLAY'] : ['EARTH', symbol];
  const report = buildChainReport(`${symbol} chain`, chain, prices, undefined, 9);

  return (
    <section className="space-y-4">
      <h1 className="text-2xl font-semibold">Chain: {symbol}</h1>
      {report.error ? (
        <p className="text-amber-300">{report.error}</p>
      ) : (
        <div className="space-y-2">
          {report.stages.map((stage) => (
            <div key={`${stage.inputSymbol}-${stage.outputSymbol}`} className="rounded border border-slate-800 bg-slate-900 p-3">
              <div className="text-sm text-slate-400">
                {stage.inputSymbol} → {stage.outputSymbol}
              </div>
              <div className="text-sm text-slate-200">
                Output amount: {Number(stage.outputAmount).toFixed(3)}
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
