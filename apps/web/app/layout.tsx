import './globals.css';
import Link from 'next/link';
import type { ReactNode } from 'react';

export const metadata = {
  title: 'CraftWorld Companion',
  description: 'CraftWorld Companion dashboard'
};

const NavLink = ({ href, label }: { href: string; label: string }) => (
  <Link className="rounded px-3 py-2 text-sm font-medium hover:bg-slate-800" href={href}>
    {label}
  </Link>
);

export default async function RootLayout({ children }: { children: ReactNode }) {
  let degraded = false;
  try {
    const res = await fetch(`${process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:3001'}/ready`, {
      cache: 'no-store'
    });
    if (res.ok) {
      const data = (await res.json()) as { degraded?: boolean };
      degraded = Boolean(data.degraded);
    }
  } catch (error) {
    degraded = true;
  }

  return (
    <html lang="en">
      <body>
        <header className="border-b border-slate-800 bg-slate-900">
          <nav className="mx-auto flex max-w-5xl flex-wrap items-center gap-2 px-4 py-4">
            <span className="text-lg font-semibold text-white">CraftWorld Companion</span>
            <div className="flex flex-wrap gap-2">
              <NavLink href="/" label="Home" />
              <NavLink href="/prices" label="Prices" />
              <NavLink href="/profitability" label="Profitability" />
              <NavLink href="/chains/MUD" label="Chains" />
              <NavLink href="/masterpieces" label="Masterpieces" />
              <NavLink href="/profile" label="Profile" />
              <NavLink href="/favorites" label="Favorites" />
            </div>
          </nav>
        </header>
        {degraded ? (
          <div className="border-b border-amber-500/40 bg-amber-500/10 text-center text-sm text-amber-200">
            Degraded mode: using cached snapshots.
          </div>
        ) : null}
        <main className="mx-auto max-w-5xl px-4 py-6">{children}</main>
      </body>
    </html>
  );
}
