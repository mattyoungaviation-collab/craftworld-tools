import Link from 'next/link';
import { fetchJson } from '../../lib/api.js';

type Masterpiece = {
  id: string;
  name: string;
  type: string;
  collectedPoints: number;
  requiredPoints: number;
  addressableLabel?: string;
};

export default async function MasterpiecesPage() {
  const data = await fetchJson<{ masterpieces: Masterpiece[] }>('/masterpieces');

  return (
    <section className="space-y-4">
      <h1 className="text-2xl font-semibold">Masterpieces</h1>
      <div className="grid gap-2 md:grid-cols-2">
        {data.masterpieces.map((mp) => (
          <Link key={mp.id} href={`/masterpieces/${mp.id}`} className="rounded border border-slate-800 bg-slate-900 p-3 hover:border-slate-600">
            <div className="text-sm text-slate-400">{mp.type}</div>
            <div className="text-lg font-semibold">{mp.name}</div>
            <div className="text-xs text-slate-400">
              {mp.collectedPoints} / {mp.requiredPoints}
            </div>
          </Link>
        ))}
      </div>
    </section>
  );
}
