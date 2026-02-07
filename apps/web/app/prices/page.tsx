import { fetchJson } from '../../lib/api';

type Price = { symbol: string; price: number };

export default async function PricesPage() {
  const data = await fetchJson<{ exchangePriceList: Price[] }>('/prices');

  return (
    <section className="space-y-4">
      <h1 className="text-2xl font-semibold">Prices</h1>
      <div className="grid gap-2 md:grid-cols-2">
        {data.exchangePriceList.map((item) => (
          <div key={item.symbol} className="rounded border border-slate-800 bg-slate-900 p-3">
            <div className="text-sm text-slate-400">{item.symbol}</div>
            <div className="text-lg font-semibold text-white">{item.price}</div>
          </div>
        ))}
      </div>
    </section>
  );
}
