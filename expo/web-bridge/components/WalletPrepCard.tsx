'use client';

import { useMemo, useState } from 'react';

type WalletState = 'idle' | 'connecting' | 'ready';

const STATE_COPY: Record<WalletState, string> = {
  idle: 'No wallet connected yet. This bridge is prepared for future token features.',
  connecting: 'Preparing secure connection flow... (placeholder only)',
  ready: 'Wallet placeholder connected. Claim and token actions are intentionally disabled for now.',
};

export default function WalletPrepCard() {
  const [walletState, setWalletState] = useState<WalletState>('idle');

  const buttonLabel = useMemo(() => {
    if (walletState === 'idle') return 'Connect Wallet';
    if (walletState === 'connecting') return 'Connecting...';
    return 'Reset Placeholder';
  }, [walletState]);

  function handleConnectClick(): void {
    if (walletState === 'ready') {
      setWalletState('idle');
      return;
    }

    setWalletState('connecting');
    window.setTimeout(() => {
      setWalletState('ready');
    }, 650);
  }

  return (
    <section className="content-card wallet-card" aria-live="polite">
      <h3>Wallet Bridge (Future-Ready)</h3>
      <p>
        This UI reserves space for wallet identity and signing. No claims, transfers, or payout actions are available in this step.
      </p>

      <div className="wallet-state-row">
        <span className={`wallet-pill wallet-${walletState}`}>{walletState.toUpperCase()}</span>
        <button
          type="button"
          className="primary-button"
          onClick={handleConnectClick}
          disabled={walletState === 'connecting'}
        >
          {buttonLabel}
        </button>
      </div>

      <p className="muted-copy">{STATE_COPY[walletState]}</p>
      <p className="muted-copy">Boundary: wallet UI is present, gameplay and token economics remain on backend/mobile paths.</p>
    </section>
  );
}