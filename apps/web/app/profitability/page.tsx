import { fetchJson } from '../../lib/api.js';
import { planCraft } from '@craftworld/shared';

type Price = { symbol: string; price: number };

export default async function ProfitabilityPage() {
  const data = await fetchJson<{ exchangePriceList: Price[] }>('/prices');
  const prices = Object.fromEntries(data.exchangePriceList.map((item) => [item.symbol, item.price]));
  const plan = planCraft('MUD', 10, prices, 'craft');

  return (
    <section className="space-y-4">
      <h1 className="text-2xl font-semibold">Profitability</h1>
      <div className="rounded border border-slate-800 bg-slate-900 p-4">
        <h2 className="text-lg font-semibold">Sample: MUD (x10)</h2>
        <div className="grid gap-2 text-sm text-slate-300">
          <div>Coin cost: {plan.totals.coinCost.toFixed(2)}</div>
          <div>Coin value: {plan.totals.coinValue.toFixed(2)}</div>
          <div>Gross profit: {plan.totals.grossProfit.toFixed(2)}</div>
        </div>
      </div>
    </section>
  );
}
