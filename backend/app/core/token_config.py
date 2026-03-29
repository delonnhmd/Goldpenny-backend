"""app/core/token_config.py — Dual-currency role definitions.

Gold Penny runs two distinct currencies:

  XGP  (off-chain)
       The gameplay currency.  Used for wages, goods, services, taxes,
       repairs, business operations, marketplace fees, maintenance, and
       healthcare.  Stored entirely in the database. Players spend and earn
       XGP through every normal gameplay action.

  PFT  (on-chain ERC-20)
       The reward token (Penny Float Token).  NOT used for daily in-game
       spending.  Players do not receive PFT directly from individual actions.
       Instead, PFT is distributed through a monthly reward pool: the system
       measures each player's XGP earnings and contribution score, then
       allocates PFT proportionally at the end of each epoch.

       Direct XGP→PFT conversion is intentionally DISABLED to prevent
       uncontrolled token inflation; the monthly pool model creates a hard
       supply ceiling per period.
"""

TOKEN_CONFIG: dict = {
    # Off-chain gameplay currency symbol.
    "offchain_currency": "XGP",

    # On-chain ERC-20 reward token symbol.
    "reward_token": "PFT",

    # Distribution model: proportional share of a capped monthly pool.
    "reward_model": "monthly_pool",

    # MUST remain False.  A fixed XGP→PFT rate would allow infinite token
    # extraction through gameplay grinding; the pool model prevents that.
    "direct_conversion_enabled": False,

    # Epochs run on a monthly cadence.
    "claim_frequency": "monthly",
}
