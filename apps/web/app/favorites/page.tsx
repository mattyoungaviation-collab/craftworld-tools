'use client';

import { useEffect, useState } from 'react';

const STORAGE_KEY = 'cw-favorites';

export default function FavoritesPage() {
  const [favorites, setFavorites] = useState<string[]>([]);
  const [input, setInput] = useState('');

  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) setFavorites(JSON.parse(stored));
  }, []);

  const save = (next: string[]) => {
    setFavorites(next);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  };

  const addFavorite = () => {
    if (!input) return;
    const next = Array.from(new Set([...favorites, input.toUpperCase()]));
    save(next);
    setInput('');
  };

  return (
    <section className="space-y-4">
      <h1 className="text-2xl font-semibold">Favorites</h1>
      <div className="flex gap-2">
        <input
          className="flex-1 rounded border border-slate-700 bg-slate-900 p-2 text-sm"
          placeholder="Symbol"
          value={input}
          onChange={(event) => setInput(event.target.value)}
        />
        <button
          className="rounded bg-sky-500 px-4 py-2 text-sm font-semibold text-white hover:bg-sky-400"
          onClick={addFavorite}
        >
          Add
        </button>
      </div>
      <ul className="space-y-1 text-sm text-slate-300">
        {favorites.map((fav) => (
          <li key={fav} className="rounded border border-slate-800 bg-slate-900 px-3 py-2">
            {fav}
          </li>
        ))}
      </ul>
    </section>
  );
}
