import Link from 'next/link';
import { ReactNode } from 'react';

interface BridgeShellProps {
  title: string;
  subtitle: string;
  children: ReactNode;
}

export default function BridgeShell({ title, subtitle, children }: BridgeShellProps) {
  return (
    <div className="page-shell">
      <header className="site-header">
        <div className="brand-wrap">
          <p className="brand-kicker">Gold Penny Web Bridge</p>
          <h1 className="brand-title">Gold Penny</h1>
        </div>
        <nav className="site-nav" aria-label="Primary">
          <Link href="/">Landing</Link>
          <Link href="/game">Game Dashboard</Link>
          <Link href="/connect">Wallet Connect</Link>
        </nav>
      </header>

      <main className="page-content">
        <section className="hero-card">
          <p className="hero-eyebrow">Companion Surface</p>
          <h2>{title}</h2>
          <p>{subtitle}</p>
        </section>
        {children}
      </main>

      <footer className="site-footer">
        <p>Web reads state. Mobile runs gameplay. Backend is source of truth.</p>
      </footer>
    </div>
  );
}