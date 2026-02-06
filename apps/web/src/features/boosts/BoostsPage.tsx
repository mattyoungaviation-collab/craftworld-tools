import { useEffect, useMemo, useState } from 'react';
import {
  getFactoryDisplayOrder,
  parseFactoriesFromCsv,
  type BoostLevels,
} from '@craftworld/shared';
import factoriesCsv from '@craftworld/data/factories.csv?raw';
import { fetchAccountProficiencies, fetchAccountWorkshop, syncBoosts } from '../../services/apiClient';

const BOOST_STORAGE_PREFIX = 'cw_boosts:';

function getBoostStorageKey(wallet: string) {
  return `${BOOST_STORAGE_PREFIX}${wallet}`;
}

function normalizeWallet(value: string | null) {
  return String(value || '').trim().toLowerCase();
}

function defaultBoosts(tokens: string[]): BoostLevels {
  return tokens.reduce((acc, token) => {
    acc[token] = { mastery_level: 0, workshop_level: 0 };
    return acc;
  }, {} as BoostLevels);
}

export default function BoostsPage() {
  const factories = useMemo(() => parseFactoriesFromCsv(factoriesCsv), []);
  const tokens = useMemo(() => getFactoryDisplayOrder(factories), [factories]);
  const [boosts, setBoosts] = useState<BoostLevels>(() => defaultBoosts(tokens));
  const [status, setStatus] = useState<string>('');
  const [lastSynced, setLastSynced] = useState<string>('never');

  useEffect(() => {
    const wallet = normalizeWallet(localStorage.getItem('cw_active_wallet'));
    if (!wallet) return;
    const raw = localStorage.getItem(getBoostStorageKey(wallet));
    if (!raw) return;
    try {
      const parsed = JSON.parse(raw) as {
        workshopLevels?: Record<string, number>;
        masteryLevels?: Record<string, number>;
        syncedAt?: number;
      };
      const next = defaultBoosts(tokens);
      for (const token of tokens) {
        if (parsed.workshopLevels && token in parsed.workshopLevels) {
          next[token].workshop_level = Number(parsed.workshopLevels[token] || 0);
        }
        if (parsed.masteryLevels && token in parsed.masteryLevels) {
          next[token].mastery_level = Number(parsed.masteryLevels[token] || 0);
        }
      }
      setBoosts(next);
      if (parsed.syncedAt) setLastSynced(new Date(parsed.syncedAt).toLocaleString());
    } catch (_err) {
      setStatus('Failed to read cached boosts.');
    }
  }, [tokens]);

  const handleChange = (token: string, field: 'mastery_level' | 'workshop_level', value: number) => {
    setBoosts((prev) => ({
      ...prev,
      [token]: { ...prev[token], [field]: value },
    }));
  };

  const handleSync = async () => {
    const token = localStorage.getItem('cw_token') || '';
    const wallet = normalizeWallet(localStorage.getItem('cw_active_wallet'));
    if (!token) {
      setStatus('Not connected. Connect Ronin Wallet.');
      return;
    }

    try {
      const [workshop, proficiencies] = await Promise.all([
        fetchAccountWorkshop(token),
        fetchAccountProficiencies(token),
      ]);

      if (!workshop.ok || !proficiencies.ok) {
        setStatus('Failed to fetch boosts.');
        return;
      }

      const workshopLevels: Record<string, number> = {};
      const masteryLevels: Record<string, number> = {};

      (workshop.workshop || []).forEach((row: { symbol: string; level: number }) => {
        workshopLevels[row.symbol.toUpperCase()] = Number(row.level || 0);
      });
      (proficiencies.proficiencies || []).forEach((row: { symbol: string; claimedLevel: number }) => {
        masteryLevels[row.symbol.toUpperCase()] = Number(row.claimedLevel || 0);
      });

      const next = defaultBoosts(tokens);
      for (const tokenKey of tokens) {
        if (workshopLevels[tokenKey] !== undefined) {
          next[tokenKey].workshop_level = workshopLevels[tokenKey];
        }
        if (masteryLevels[tokenKey] !== undefined) {
          next[tokenKey].mastery_level = masteryLevels[tokenKey];
        }
      }
      setBoosts(next);
      const payload = { workshopLevels, masteryLevels, syncedAt: Date.now() };
      if (wallet) {
        localStorage.setItem(getBoostStorageKey(wallet), JSON.stringify(payload));
      }
      await syncBoosts({ workshopLevels, masteryLevels });
      setLastSynced(new Date(payload.syncedAt).toLocaleString());
      setStatus('');
    } catch (_err) {
      setStatus('Failed to sync boosts.');
    }
  };

  const handleSave = async () => {
    const masteryLevels: Record<string, number> = {};
    const workshopLevels: Record<string, number> = {};
    for (const token of tokens) {
      masteryLevels[token] = boosts[token]?.mastery_level ?? 0;
      workshopLevels[token] = boosts[token]?.workshop_level ?? 0;
    }
    await syncBoosts({ masteryLevels, workshopLevels });
    setStatus('Boosts saved.');
  };

  return (
    <section className="card">
      <h2>Mastery & Workshop Boosts</h2>
      <p className="muted">Auto-fill from Craft World or edit manually.</p>
      {status && <div className="status">{status}</div>}
      <div className="form-grid">
        <button type="button" onClick={handleSync}>
          Auto-fill from Craft World
        </button>
        <button type="button" onClick={handleSave}>
          Save boosts
        </button>
        <div className="muted">Last synced: {lastSynced}</div>
      </div>
      <div className="table-wrapper">
        <table className="table">
          <thead>
            <tr>
              <th>Token</th>
              <th>Mastery (0-10)</th>
              <th>Workshop (0-10)</th>
            </tr>
          </thead>
          <tbody>
            {tokens.map((token) => (
              <tr key={token}>
                <td>{token}</td>
                <td>
                  <select
                    value={boosts[token]?.mastery_level ?? 0}
                    onChange={(event) => handleChange(token, 'mastery_level', Number(event.target.value))}
                  >
                    {Array.from({ length: 11 }, (_, idx) => (
                      <option key={idx} value={idx}>
                        {idx}
                      </option>
                    ))}
                  </select>
                </td>
                <td>
                  <select
                    value={boosts[token]?.workshop_level ?? 0}
                    onChange={(event) => handleChange(token, 'workshop_level', Number(event.target.value))}
                  >
                    {Array.from({ length: 11 }, (_, idx) => (
                      <option key={idx} value={idx}>
                        {idx}
                      </option>
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
