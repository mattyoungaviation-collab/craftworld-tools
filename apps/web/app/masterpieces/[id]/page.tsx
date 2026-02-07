import { fetchJson } from '../../../lib/api.js';

type Params = { params: { id: string } };

export default async function MasterpieceDetailPage({ params }: Params) {
  const data = await fetchJson<{ masterpiece: { name: string; type: string; resources: { symbol: string; amount: number }[] } }>(
    `/masterpieces/${params.id}`
  );

  return (
    <section className="space-y-4">
      <h1 className="text-2xl font-semibold">{data.masterpiece.name}</h1>
      <p className="text-sm text-slate-400">{data.masterpiece.type}</p>
      <div className="rounded border border-slate-800 bg-slate-900 p-4">
        <h2 className="text-lg font-semibold">Resources</h2>
        <ul className="mt-2 space-y-1 text-sm text-slate-300">
          {data.masterpiece.resources?.map((resource) => (
            <li key={resource.symbol}>
              {resource.symbol}: {resource.amount}
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
