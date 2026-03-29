// Gold Penny — centralized gameplay balance configuration.
// All tunable values for the active gameplay loop live here.
// Change numbers here to tune progression; avoid scattering literals elsewhere.

export const BALANCE = {
  // ─── Daily time budget ────────────────────────────────────────────────────────
  DEFAULT_TOTAL_TIME_UNITS: 10,
  MIN_TOTAL_TIME_UNITS: 6,
  MAX_TOTAL_TIME_UNITS: 16,

  // ─── Time cost per action type (units consumed per use) ───────────────────────
  ACTION_TIME_COST: {
    work_shift: 3,       // heavy — takes most of a half-day slot
    side_income: 3,
    operate_business: 2,
    buy_inventory: 1,
    rest: 2,
    study: 2,
    debt_payment: 1,
    recovery_action: 1,
    switch_job: 1,
    change_region: 1,
  } as Record<string, number>,

  // ─── Per-day caps per action type ─────────────────────────────────────────────
  // Caps are the primary guard against action spam.
  ACTION_CAPS: {
    work_shift: 2,        // max 2 × 3 = 6 units per day on work
    side_income: 2,
    operate_business: 1,
    buy_inventory: 2,
    rest: 2,
    study: 2,
    debt_payment: 1,      // once per day; prevents free debt-loop
    recovery_action: 1,   // one session-level recovery per day
    switch_job: 1,
    change_region: 1,
  } as Record<string, number>,

  // ─── Random event cash / debt impact (informational display values) ───────────
  EVENT: {
    GROCERY_SPIKE_LOSS: 25,
    MISSED_OPPORTUNITY_LOSS: 15,
    UNEXPECTED_BILL_LOSS: 75,
    CAR_REPAIR_LOSS: 120,
    EXTRA_SHIFT_GAIN: 50,
    SIDE_INCOME_GAIN: 40,
    MINOR_DEBT_FEE: 30,
    FINANCIAL_RELIEF: 40,
  },

  // ─── Recovery action values ────────────────────────────────────────────────────
  RECOVERY: {
    CUT_SPENDING_GAIN: 30,       // modest saving — below a typical shift earn
    SIDE_HUSTLE_GAIN: 45,        // slightly above CUT_SPENDING but a real tradeoff
    SKIP_EXPENSE_GAIN: 20,       // smallest recovery — lowest-effort option
    DEBT_PAYMENT_COST: 50,       // cash spent
    DEBT_PAYMENT_REDUCTION: 55,  // debt cleared — small incentive to use action
    DEBT_PAYMENT_MIN_CASH: 50,   // won't appear unless player can afford it
  },

  // ─── Warning / pressure thresholds ────────────────────────────────────────────
  THRESHOLDS: {
    LOW_CASH_WARNING_XGP: 300,   // show low-cash warning before one bad day becomes a crisis
    DEBT_HIGH_RATIO: 0.5,        // debt > 50 % of cash = high pressure
    DEBT_CRITICAL_RATIO: 1.0,    // debt >= cash = critical pressure
  },

  // ─── Runtime safety boundaries ───────────────────────────────────────────────
  SAFETY: {
    MAX_ABSOLUTE_XGP: 1000000,
    MAX_ABSOLUTE_DELTA_XGP: 250000,
    MIN_PERCENTAGE_STAT: 0,
    MAX_PERCENTAGE_STAT: 100,
    MIN_CREDIT_SCORE: 300,
    MAX_CREDIT_SCORE: 850,
    MIN_TIME_COST_UNITS: 1,
    MAX_TIME_COST_UNITS: 4,
    MAX_GAME_DAY: 36500,
    MAX_NET_CASHFLOW_MISMATCH_XGP: 1000,
  },
} as const;
