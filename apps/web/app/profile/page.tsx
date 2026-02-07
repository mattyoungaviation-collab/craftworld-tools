'use client';

import { useEffect, useState } from 'react';

const STORAGE_KEY = 'cw-profile';

export default function ProfilePage() {
  const [profile, setProfile] = useState('');

  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) setProfile(stored);
  }, []);

  const save = () => {
    localStorage.setItem(STORAGE_KEY, profile);
  };

  return (
    <section className="space-y-4">
      <h1 className="text-2xl font-semibold">Profile</h1>
      <p className="text-sm text-slate-400">
        Edit your workshop and mastery details locally. Sync to server when auth is enabled.
      </p>
      <textarea
        className="h-40 w-full rounded border border-slate-700 bg-slate-900 p-3 text-sm"
        value={profile}
        onChange={(event) => setProfile(event.target.value)}
        placeholder="Paste JSON profile settings"
      />
      <button
        className="rounded bg-sky-500 px-4 py-2 text-sm font-semibold text-white hover:bg-sky-400"
        onClick={save}
      >
        Save locally
      </button>
    </section>
  );
}
