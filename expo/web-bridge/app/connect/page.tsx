import Link from 'next/link';

import BridgeShell from '@/components/BridgeShell';
import WalletPrepCard from '@/components/WalletPrepCard';

export default function ConnectPage() {
  return (
    <BridgeShell
      title="Wallet Connect Prep"
      subtitle="Future-ready connection surface for token integration, intentionally isolated from gameplay execution and claim flows."
    >
      <section className="content-grid">
        <WalletPrepCard />

        <article className="content-card content-col-6">
          <h3>Why This Exists Now</h3>
          <ul className="copy-list">
            <li>Reserve wallet UX space before full token rollout.</li>
            <li>Let soft-launch users recognize upcoming integration points.</li>
            <li>Keep implementation light so mobile logic stays untouched.</li>
          </ul>
        </article>

        <article className="content-card content-col-6">
          <h3>What Is Not Included</h3>
          <ul className="copy-list">
            <li>No claim, payout, or transfer actions.</li>
            <li>No local token math or economy simulation.</li>
            <li>No replacement of mobile progression or action runtime.</li>
          </ul>
          <div className="button-row">
            <Link href="/game" className="secondary-button">
              Back to /game
            </Link>
          </div>
        </article>
      </section>
    </BridgeShell>
  );
}