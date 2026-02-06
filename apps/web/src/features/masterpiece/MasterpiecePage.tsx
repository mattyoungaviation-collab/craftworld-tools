import { useEffect, useState } from 'react';
import { fetchMasterpieceDetails, fetchMasterpieces } from '../../services/masterpiece';

export default function MasterpiecePage() {
  const [masterpieces, setMasterpieces] = useState<Record<string, unknown>[]>([]);
  const [selectedId, setSelectedId] = useState<string>('');
  const [details, setDetails] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    fetchMasterpieces()
      .then((data) => {
        setMasterpieces(data);
        if (data[0]?.id) setSelectedId(String(data[0].id));
      })
      .catch((err) => setError(String(err)));
  }, []);

  useEffect(() => {
    if (!selectedId) return;
    fetchMasterpieceDetails(selectedId)
      .then((data) => setDetails(data || null))
      .catch((err) => setError(String(err)));
  }, [selectedId]);

  return (
    <section className="card">
      <h2>Masterpiece</h2>
      {error && <p className="status">{error}</p>}
      <label>
        Select Masterpiece
        <select value={selectedId} onChange={(event) => setSelectedId(event.target.value)}>
          {masterpieces.map((mp) => (
            <option key={String(mp.id)} value={String(mp.id)}>
              {String(mp.name || mp.addressableLabel || mp.id)}
            </option>
          ))}
        </select>
      </label>
      {details ? (
        <div className="card" style={{ marginTop: '16px' }}>
          <h3>{String(details.name || details.addressableLabel || details.id)}</h3>
          <p className="muted">Type: {String(details.type || '—')}</p>
          <p className="muted">
            Points: {String(details.collectedPoints || 0)} / {String(details.requiredPoints || 0)}
          </p>
          <div className="table-wrapper">
            <table className="table">
              <thead>
                <tr>
                  <th>Resource</th>
                  <th>Collected</th>
                  <th>Target</th>
                </tr>
              </thead>
              <tbody>
                {(details.resources as Record<string, unknown>[] | undefined)?.map((resource) => (
                  <tr key={String(resource.symbol)}>
                    <td>{String(resource.symbol || '')}</td>
                    <td>{String(resource.amount || 0)}</td>
                    <td>{String(resource.target || 0)}</td>
                  </tr>
                )) || null}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <p className="muted">Loading masterpiece details...</p>
      )}
    </section>
  );
}
