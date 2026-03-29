# Step 76 — Hard UI Cleanup Report
## Remove All Non-Actionable / Repetitive / Consultant Text

---

## Objective

Aggressively strip every duplicated, advisory, consultant-style, or non-actionable UI element across all gameplay screens. No preview layers. No "best setup" cards. No "watch before acting" warnings. No 5-second read. No snapshot chips. No signal cards. Players click buttons, not read analysis.

---

## Files Changed

### 1. `GameplayLoopScaffold.tsx`
- **Removed** "Today At A Glance" / "5-Second Read" / "Day 1 Essentials" ternary block (~70 lines) shared across all screens
- **Removed** `headerRight` Refresh button from `AppShell`
- **Removed** unused imports: `SecondaryButton`, `formatMoney`, `Text`, `View` (RN), `GameplayCompactMetricRows`, `GameplaySummaryCard`, `GameplayTrendChip`, `toneFromSignedValue`
- **Removed** helper functions: `labelFromPressure()`, `pressureTone()`
- **Removed** unused variables: `cash`, `stress`, `netFlow`, `pressure`, `usedUnits`, `topOpportunity`, `topRisk`, `nextAction`, `syncedTimeLabel`
- **Removed** unused styles: `scanCardRow`, `scanCard`, `scanLabel`, `scanValue`, `trendRow`

### 2. `ActionHubPanel.tsx`
- **Removed** `headingBlock` with "Daily control area" eyebrow + "Action Hub" heading + subheading
- **Removed** "Best setup" highlighted card (`hub.top_tradeoffs`)
- **Removed** "Watch before acting" warning card (`hub.next_risk_warnings`)
- **Changed** `Available` and `Blocked` action sections: all sections now expand by default
- **Renamed** `onPreviewAction` → `onExecuteAction` (prop and usage in ActionSection)
- **Renamed** `onPreview` → `onExecute` inside `ActionSection`
- **Removed** unused styles: `headingBlock`, `eyebrow`, `heading`, `subheading`, `infoBox`, `infoTitle`, `infoText`, `warningBox`, `warningTitle`, `warningText`, `sectionHeaderStatic`, `sectionEyebrow`
- **Updated** `timeTitle` to show "{remaining}/{total} units left" directly (removed "Session Tempo" label)

### 3. `ActionCard.tsx`
- **Renamed** `onPreview` prop → `onExecute`
- **Changed** button label from `"Preview"` → `"Start"`
- **Changed** button callback from `onPreview(action)` → `onExecute(action)` (direct execution, no modal)
- **Renamed** `previewDisabled` → `disabled`

### 4. `DashboardScreen.tsx`
- **Removed** `import ActionPreviewModal` (no longer used)
- **Changed** `ActionHubPanel` prop: `onPreviewAction` → `onExecuteAction={(action) => void loop.executeAction(action)}`
- **Removed** entire `<ActionPreviewModal .../>` block (modal with preview/confirmation layer)

### 5. `DailyBriefCard.tsx`
- **Stripped** to `heroBlock` only: Daily Brief label + headline + summary text
- **Removed** `primarySignal` box ("Watch now" / "Best opening")
- **Removed** `bottomGrid` ("Best next move" actions list + "Secondary signal" box)
- **Removed** `impactBox` ("Driving signals" bullets)
- **Removed** `impactBullets` prop
- **Removed** all related variables: `bullets`, `recommendedActions`, `leadRisk`, `leadOpportunity`, `primarySignal`, `secondarySignal`, `primarySignalWatchValue`, `secondarySignalWatchValue`
- **Removed** all related styles (150+ lines of signal/grid styles)

### 6. `BriefScreen.tsx`
- **Removed** Economy Snapshot chips card (Day / Time left / Net flow / Market mood)
- **Removed** `timeTone` variable
- **Fixed** `DailyBriefCard` call — removed `impactBullets` prop
- **Added** `<Text>` to imports
- **Added** "Today's Activity" section showing:
  - Net flow (earned - spent)
  - Actions taken count
  - Actions taken list (title + failure flag)
  - "Transaction log — coming soon" placeholder
- **Added** styles: `actionsList`, `actionsListItem`, `txPlaceholder`

### 7. `MarketScreen.tsx`
- **Removed** "Market snapshot" chips card (Market mood / Baskets / Stocks / Holdings)
- **Removed** advisory subtitle from baskets card ("These moves affect what you pay...")
- **Removed** advisory subtitle from stocks card ("Use this after core survival...")
- **Removed** `summary` prop from `GameplayStickyActionArea` footer ("Baskets shape daily costs...")
- **Changed** CTA: `"Back To Work"` → `"Back To Dashboard"` (navigates to `dashboard`)
- **Removed** unused imports: `StyleSheet`, `View`, `theme`, `GameplayTrendChip`
- **Removed** unused variables: `marketMood`, `basketCount`, `stockCount`, `holdings`
- **Removed** `styles.chipRow` (no more chip rows)
- **Simplified** Baskets card title from "Why prices change today" → "Price Trends"
- **Simplified** Stocks card title from "Optional Stock Lane" → "Stock Lane"

### 8. `BusinessScreen.tsx`
- **Removed** import `BusinessMarginsCard`
- **Removed** import `BusinessPlanCard`
- **Removed** entire "Business Margin Signals" section (`eyebrow="Economy context"`)
- **Removed** entire "Business Plan Signals" section (`eyebrow="3-7 day view"`)
- **Removed** `summary` advisory text from `GameplayStickyActionArea` footer
- **Kept** core stats card (Revenue / Cost Pressure / Margin Outlook / 7d Profit)
- **Kept** high-cost-pressure warning banner
- **Kept** `BusinessOperationsCard` for operate action
- **Kept** `EmptyStateView` for players without a business

---

## What Was NOT Changed

- `ActionPreviewModal` component file — left intact (might be used elsewhere)
- `BusinessMarginsCard`, `BusinessPlanCard` component files — left intact
- Settlement status chips in `BriefScreen` — kept as they show real end-of-day state
- `BusinessOperationsCard` — kept (it is the operate action button)

---

## TypeScript Status

All 8 modified files: **0 errors**.

---

## Architecture After Step 76

```
Dashboard     → Stats card + Job selector + ActionHub (all actions expanded, Start button) + Meals + Loans
Brief         → News headline + Today's activity (net flow + actions list + tx placeholder) + Settlement
Market        → Price Trends + Stock Lane (no snapshot chips, no advisory subtitles)
Business      → Core stats + Warning banner + Operate card (no signal cards)
```

No preview modal. No advisory text. No 5-second reads. Every card shows either:
- A real number the player takes action on, or
- An action button they can press right now
