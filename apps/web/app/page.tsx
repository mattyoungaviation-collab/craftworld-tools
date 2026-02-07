import { fetchJson } from '../lib/api';

export default async function HomePage() {
  const ready = await fetchJson<{ ok: boolean; degraded: boolean; deps: Record<string, boolean> }>('/ready');

  return (
    <section className="space-y-4">
      <div className="rounded border border-slate-800 bg-slate-900 p-4">
        <h1 className="text-2xl font-semibold">Welcome</h1>
        <p className="text-slate-300">Real-time CraftWorld data with resilient caching.</p>
      </div>
      <div className="rounded border border-slate-800 bg-slate-900 p-4">
        <h2 className="text-lg font-semibold">Service Status</h2>
        <p className={ready.degraded ? 'text-amber-300' : 'text-emerald-300'}>
          {ready.degraded ? 'Degraded mode' : 'All systems nominal'}
        </p>
        <ul className="mt-2 text-sm text-slate-300">
          {Object.entries(ready.deps).map(([key, value]) => (
            <li key={key}>
              {key}: {value ? 'ok' : 'missing'}
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
