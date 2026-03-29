"""app/core/reward_policy.py — Monthly PFT reward pool policy.

These values govern both eligibility gating and the size of each monthly
distribution.  Edit them here and all engine / API code picks up the change
automatically.

Economic intent
---------------
* total_supply caps the absolute number of PFT that will ever exist.
* monthly_reward_pool is the maximum PFT that can leave the reserve in a
  single epoch.  The pool is split proportionally among qualified players —
  nobody can receive more than their fair share.
* The eligibility gates (account age, reputation, contribution score) exist
  to prevent sybil accounts and low-effort farming from diluting the pool for
  genuine players.
* claim_enabled is False during Step 1.  The infrastructure is built now so
  the on-chain claim flow can be activated in a later step without schema changes.
"""

REWARD_POLICY: dict = {
    # Hard cap on total PFT ever minted (100 billion units).
    "total_supply": 100_000_000_000,

    # Maximum PFT distributed to all players combined per monthly epoch.
    # Acts as an emission ceiling regardless of player count.
    "monthly_reward_pool": 50_000_000,

    # A player's account must be at least this many real-calendar days old
    # before they can qualify for PFT allocation.
    "min_account_age_days": 30,

    # Minimum reputation score required to qualify.
    # Reputation is earned through positive in-game actions and lost through
    # bad behaviour (fraud, defaults, rules violations).
    "min_reputation": 20,

    # Minimum weighted contribution score a player must reach in a given epoch.
    # Players below this threshold are excluded from pool allocation entirely,
    # which concentrates the pool in the hands of active contributors.
    "min_contribution_score": 100,

    # Master switch for the on-chain claim flow.
    # Set to True only after the smart-contract claim pipeline is audited
    # and the wallet-verification layer is live.
    "claim_enabled": False,

    # Current season number.  Increments when major economy rule changes
    # are introduced (e.g. new weight tuning, supply adjustments).
    "season_number": 1,
}
