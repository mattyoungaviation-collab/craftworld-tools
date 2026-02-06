import { useEffect, useState } from 'react';
import { fetchGraphql } from '../services/pricing';

const MASTERPIECES_QUERY = `
  query Masterpieces {
    masterpieces {
      id
      name
      type
      eventId
      collectedPoints
      requiredPoints
      addressableLabel
      startedAt
    }
  }
`;

const MASTERPIECE_DETAILS_QUERY = `
  query Masterpiece($id: ID) {
    masterpiece(id: $id) {
      id
      name
      type
      eventId
      collectedPoints
      requiredPoints
      addressableLabel
      resources {
        symbol
        amount
        target
        consumedPowerPerUnit
      }
      leaderboard {
        position
        masterpiecePoints
        profile { uid walletAddress avatarUrl displayName }
      }
      startedAt
    }
  }
`;

const PREDICT_REWARD_QUERY = `
  query MasterpieceRewardsForResources($masterpieceId: ID!, $resources: [ResourceInput!]!) {
    masterpiece(id: $masterpieceId) {
      id
      predictReward(resources: $resources) {
        masterpiecePoints
        experiencePoints
        requiredPower
        resources { symbol amount }
      }
    }
  }
`;

export default function MasterpiecePage() {
  const [list, setList] = useState<any[]>([]);
  const [selected, setSelected] = useState<string>('');
  const [details, setDetails] = useState<any | null>(null);
  const [status, setStatus] = useState('');
  const [resourcesInput, setResourcesInput] = useState('');
  const [reward, setReward] = useState<any | null>(null);

  useEffect(() => {
    async function load() {
      try {
        setStatus('Loading masterpieces...');
        const data = await fetchGraphql(MASTERPIECES_QUERY);
        const items = data.masterpieces || [];
        setList(items.sort((a: any, b: any) => String(b.startedAt || '').localeCompare(String(a.startedAt || ''))));
        setStatus('Masterpieces loaded.');
      } catch (err: any) {
        setStatus(String(err?.message || err));
      }
    }
    load();
  }, []);

  async function loadDetails(id: string) {
    try {
      setStatus('Loading details...');
      const data = await fetchGraphql(MASTERPIECE_DETAILS_QUERY, { id });
      setDetails(data.masterpiece || null);
      setStatus('Details loaded.');
    } catch (err: any) {
      setStatus(String(err?.message || err));
    }
  }

  async function predictReward() {
    if (!selected) return;
    try {
      const resources = resourcesInput
        .split('\n')
        .map((line) => line.trim())
        .filter(Boolean)
        .map((line) => {
          const [symbol, amount] = line.split(',').map((part) => part.trim());
          return { symbol: symbol.toUpperCase(), amount: Number(amount || 0) };
        });
      const data = await fetchGraphql(PREDICT_REWARD_QUERY, {
        masterpieceId: selected,
        resources,
      });
      setReward(data.masterpiece?.predictReward || null);
    } catch (err: any) {
      setStatus(String(err?.message || err));
    }
  }

  return (
    <section className="card">
      <h2>Masterpiece</h2>
      <p className="muted">Inspect masterpiece details and predict rewards.</p>
      <div className="notice">{status || 'Ready.'}</div>
      <label>
        Select Masterpiece
        <select
          value={selected}
          onChange={(e) => {
            setSelected(e.target.value);
            if (e.target.value) loadDetails(e.target.value);
          }}
        >
          <option value="">Choose...</option>
          {list.map((mp) => (
            <option key={mp.id} value={mp.id}>
              {mp.name || `#${mp.id}`}
            </option>
          ))}
        </select>
      </label>
      {details && (
        <div className="card" style={{ marginTop: 16 }}>
          <h3>{details.name || `#${details.id}`}</h3>
          <p className="muted">Type: {details.type} • Points: {details.collectedPoints}/{details.requiredPoints}</p>
          <table className="table">
            <thead>
              <tr>
                <th>Resource</th>
                <th>Amount</th>
                <th>Target</th>
              </tr>
            </thead>
            <tbody>
              {(details.resources || []).map((row: any) => (
                <tr key={row.symbol}>
                  <td>{row.symbol}</td>
                  <td>{Number(row.amount || 0).toLocaleString()}</td>
                  <td>{Number(row.target || 0).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="card" style={{ marginTop: 16 }}>
        <h3>Predict Reward</h3>
        <p className="muted">Enter lines like: <code>SEAWATER, 100</code></p>
        <textarea
          rows={4}
          value={resourcesInput}
          onChange={(e) => setResourcesInput(e.target.value)}
          style={{ width: '100%' }}
        />
        <button type="button" onClick={predictReward} style={{ marginTop: 8 }}>Predict</button>
        {reward && (
          <div style={{ marginTop: 12 }}>
            <p className="muted">Masterpiece Points: {Number(reward.masterpiecePoints || 0).toLocaleString()}</p>
            <p className="muted">XP: {Number(reward.experiencePoints || 0).toLocaleString()}</p>
            <p className="muted">Required Power: {Number(reward.requiredPower || 0).toLocaleString()}</p>
          </div>
        )}
      </div>
    </section>
  );
}
