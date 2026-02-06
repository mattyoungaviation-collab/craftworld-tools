import { useEffect, useMemo, useState } from 'react';
import { FACTORY_ORDER } from '../services/factoriesData';
import { apiClient } from '../services/apiClient';
import { getBoostStorageKey, getActiveWallet } from '../services/storage';
import { getSession } from '../services/wallet';

interface BoostLevels {
  mastery: Record<string, number>;
  workshop: Record<string, number>;
  syncedAt?: number;
}

const clampLevel = (value: number) => Math.max(0, Math.min(10, Math.trunc(value)));

const buildDefaultLevels = () => {
  const mastery: Record<string, number> = {};
  const workshop: Record<string, number> = {};
  for (const token of FACTORY_ORDER) {
    mastery[token] = 0;
    workshop[token] = 0;
  }
  return { mastery, workshop };
};

export default function BoostsPage() {
  const [levels, setLevels] = useState<BoostLevels>(() => ({
    ...buildDefaultLevels(),
    syncedAt: undefined,
  }));
  const [status, setStatus] = useState<string>('');

  const wallet = useMemo(() => getActiveWallet(), []);

  useEffect(() => {
    if (!wallet) return;
    const stored = localStorage.getItem(getBoostStorageKey(wallet));
    if (stored) {
      try {
        const parsed = JSON.parse(stored) as BoostLevels;
        setLevels({
          mastery: { ...buildDefaultLevels().mastery, ...(parsed.mastery || parsed.masteryLevels || {}) },
          workshop: { ...buildDefaultLevels().workshop, ...(parsed.workshop || parsed.workshopLevels || {}) },
          syncedAt: parsed.syncedAt,
        });
      } catch {
        // ignore
      }
    }
  }, [wallet]);

  async function syncFromCraftWorld() {
    const session = getSession();
    if (!session.cwToken) {
      setStatus('Not connected. Connect Ronin Wallet.');
      return;
    }

    try {
      setStatus('Syncing mastery + workshop...');
      const [workshopData, profData] = await Promise.all([
        apiClient.accountWorkshop(session.cwToken),
        apiClient.accountProficiencies(session.cwToken),
      ]);

      const workshop: Record<string, number> = {};
      for (const row of workshopData.workshop || []) {
        const symbol = String(row.symbol || '').toUpperCase();
        if (!symbol) continue;
        workshop[symbol] = clampLevel(Number(row.level || 0));
      }

      const mastery: Record<string, number> = {};
      for (const row of profData.proficiencies || []) {
        const symbol = String(row.symbol || '').toUpperCase();
        if (!symbol) continue;
        mastery[symbol] = clampLevel(Number(row.claimedLevel || 0));
      }

      const next: BoostLevels = {
        mastery: { ...buildDefaultLevels().mastery, ...mastery },
        workshop: { ...buildDefaultLevels().workshop, ...workshop },
        syncedAt: Date.now(),
      };
      setLevels(next);

      if (wallet) {
        localStorage.setItem(getBoostStorageKey(wallet), JSON.stringify({
          masteryLevels: mastery,
          workshopLevels: workshop,
          syncedAt: next.syncedAt,
        }));
      }

      await apiClient.syncBoosts({ masteryLevels: mastery, workshopLevels: workshop });
      setStatus('Mastery + workshop synced.');
    } catch (err: any) {
      setStatus(String(err?.message || err));
    }
  }

  function updateLevel(token: string, type: 'mastery' | 'workshop', value: number) {
    setLevels((prev) => ({
      ...prev,
      [type]: { ...prev[type], [token]: clampLevel(value) },
    }));
  }

  function persistLevels() {
    if (!wallet) {
      setStatus('No active wallet. Connect and retry.');
      return;
    }
    const payload = {
      masteryLevels: levels.mastery,
      workshopLevels: levels.workshop,
      syncedAt: Date.now(),
    };
    localStorage.setItem(getBoostStorageKey(wallet), JSON.stringify(payload));
    setStatus('Boosts saved locally.');
  }

  return (
    <section className="card">
      <h2>Boosts</h2>
      <p className="muted">Auto-fill from Craft World or edit manually per token.</p>
      <div className="notice">{status || 'Ready.'}</div>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
        <button type="button" onClick={syncFromCraftWorld}>Sync from Craft World</button>
        <button type="button" className="secondary" onClick={persistLevels}>Save locally</button>
        {levels.syncedAt ? (
          <span className="muted">Last synced: {new Date(levels.syncedAt).toLocaleString()}</span>
        ) : null}
      </div>
      <div style={{ maxHeight: 460, overflow: 'auto' }}>
        <table className="table">
          <thead>
            <tr>
              <th>Token</th>
              <th>Mastery</th>
              <th>Workshop</th>
            </tr>
          </thead>
          <tbody>
            {FACTORY_ORDER.map((token) => (
              <tr key={token}>
                <td>{token}</td>
                <td>
                  <select
                    value={levels.mastery[token] ?? 0}
                    onChange={(event) => updateLevel(token, 'mastery', Number(event.target.value))}
                  >
                    {Array.from({ length: 11 }).map((_, i) => (
                      <option key={i} value={i}>{i}</option>
                    ))}
                  </select>
                </td>
                <td>
                  <select
                    value={levels.workshop[token] ?? 0}
                    onChange={(event) => updateLevel(token, 'workshop', Number(event.target.value))}
                  >
                    {Array.from({ length: 11 }).map((_, i) => (
                      <option key={i} value={i}>{i}</option>
                    ))}
                  </select>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
