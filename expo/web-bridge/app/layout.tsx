import type { Metadata } from 'next';
import { Plus_Jakarta_Sans, Sora } from 'next/font/google';
import { ReactNode } from 'react';

import { getCanonicalHost } from '@/lib/config';

import './globals.css';

const headingFont = Sora({
  subsets: ['latin'],
  variable: '--font-heading',
  weight: ['500', '600', '700', '800'],
});

const bodyFont = Plus_Jakarta_Sans({
  subsets: ['latin'],
  variable: '--font-body',
  weight: ['400', '500', '600', '700'],
});

const canonicalHost = getCanonicalHost();
const metadataBase = canonicalHost.startsWith('http')
  ? new URL(canonicalHost)
  : new URL(`https://${canonicalHost}`);

export const metadata: Metadata = {
  metadataBase,
  title: {
    default: 'Gold Penny Web Bridge',
    template: '%s | Gold Penny',
  },
  description:
    'Gold Penny web companion for Daily Brief, player snapshot, and future wallet integration. Gameplay remains mobile-first.',
  alternates: {
    canonical: '/',
  },
  openGraph: {
    title: 'Gold Penny Web Bridge',
    description:
      'Read-only companion surface for Gold Penny game state with deep links back to mobile gameplay.',
    url: '/',
    siteName: 'Gold Penny',
    type: 'website',
  },
  twitter: {
    card: 'summary',
    title: 'Gold Penny Web Bridge',
    description: 'Daily Brief, player snapshot, and mobile deep-link companion for Gold Penny.',
  },
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className={`${headingFont.variable} ${bodyFont.variable} app-root`}>{children}</body>
    </html>
  );
}