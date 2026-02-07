// NOTE:
// The Next.js app imports from "../lib/api.js" explicitly.
// Keeping this file as a real JS module avoids ESM/NodeNext re-export
// edge-cases during prerender/build on Render.

export const apiBase = () => process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:3001';

export const fetchJson = async (path) => {
  const res = await fetch(`${apiBase()}${path}`, { cache: 'no-store' });
  if (!res.ok) throw new Error(`Request failed: ${res.status}`);
  return await res.json();
};
