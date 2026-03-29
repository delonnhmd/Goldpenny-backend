# FIGMA Design System Report - Step 61

## Objective
Map the existing Gold Penny Expo gameplay UI into a reusable Figma design system and screen set, without inventing new UI and without changing the locked Step 58 portrait structure.

## Outcome
Step 61 mapping is complete at the specification level and ready for direct Figma construction.

Figma MCP execution status in this environment:
- `FIGMA_OAUTH_TOKEN` is not available
- Figma MCP server is not configured in `C:\Users\mdnoi\.codex\config.toml`

Because MCP is not authenticated here, this report is a code-accurate build spec derived from the live UI implementation and locked reports (Steps 54, 55, 58, 59, 60).

## Source of Truth Reviewed
- `src/design/tokens.ts`
- `src/design/theme.ts`
- `src/pages/gameplay/GameDashboardPage.tsx`
- `src/lib/ui_layout_config.ts`
- `src/components/gameplay/DailyBriefCard.tsx`
- `src/components/gameplay/PlayerStatsBar.tsx`
- `src/components/gameplay/ActionHubPanel.tsx`
- `src/components/gameplay/ThumbReachActionDock.tsx`
- `src/components/gameplay/BusinessOperationsCard.tsx`
- `src/components/gameplay/StockMarketCard.tsx`
- `src/components/gameplay/EndOfDaySummaryCard.tsx`
- `src/components/gameplay/OnboardingBanner.tsx`
- `src/components/ui/PrimaryButton.tsx`
- `src/components/ui/SecondaryButton.tsx`
- `src/components/ui/SurfaceCard.tsx`
- `src/components/layout/BottomActionBar.tsx`

## Part 1 - Design System Foundation

### Core Tokens

#### Color Tokens (base)
- Background: `#f1f5f9`
- Surface: `#ffffff`
- Surface Alt: `#f8fafc`
- Text Primary: `#0f172a`
- Text Secondary: `#475569`
- Border: `#cbd5e1`
- Positive: `#16a34a`
- Warning: `#ca8a04`
- Danger: `#dc2626`
- Info: `#2563eb`
- Accent: `#1d4ed8`
- Muted: `#94a3b8`

#### Gameplay Semantic Color Usage (component-level)
- Primary blue callouts and action emphasis: `#1d4ed8`, `#eff6ff`, `#bfdbfe`
- Success states: `#166534`, `#f0fdf4`, `#86efac`
- Warning states: `#92400e`, `#78350f`, `#fffbeb`, `#fcd34d`, `#fde68a`
- Danger states: `#b91c1c`, `#7f1d1d`, `#fef2f2`, `#fecaca`

#### Spacing
- `2, 4, 8, 12, 16, 20, 24, 32`

#### Radius
- Small: `6`
- Medium: `10`
- Large: `12`
- XL: `16`
- Pill: `999`

#### Elevation
- `sm`: y=2, blur=4, opacity `0.06`, elevation `1`
- `md`: y=4, blur=8, opacity `0.10`, elevation `3`
- `lg`: y=8, blur=12, opacity `0.14`, elevation `5`

#### Typography
- Headline large: `22/28`, `800`
- Headline medium: `18/24`, `700`
- Headline small: `16/22`, `700`
- Body medium: `14/20`, `400`
- Body small: `12/18`, `400`
- Label: `12/16`, `700`
- Caption: `11/14`, `600`

## Part 2 - Core Components (Figma Component Set)

### 1) `DailyBriefCard`
Source: `src/components/gameplay/DailyBriefCard.tsx`

Variants:
- Primary signal `risk`
- Primary signal `opportunity`
- Secondary signal `present/empty`
- Driving signals `present/absent`

### 2) `PlayerStatsBar` / Player Snapshot
Source: `src/components/gameplay/PlayerStatsBar.tsx`

Variants:
- Pressure tone `stable/high/critical`
- Net flow tone `positive/neutral/negative`
- Mobile vs non-mobile detail pills

### 3) Action Button
Sources:
- `src/components/ui/PrimaryButton.tsx`
- `src/components/ui/SecondaryButton.tsx`

Variants:
- `Primary`: normal, pressed, disabled, loading
- `Secondary`: normal, pressed, disabled, loading

### 4) `BottomActionBar` + `ThumbReachActionDock`
Sources:
- `src/components/layout/BottomActionBar.tsx`
- `src/components/gameplay/ThumbReachActionDock.tsx`

Variants:
- Feedback `none/info/success/error`
- Highlighted action `on/off`
- Session state `active/ended`

### 5) `BusinessOperationsCard`
Source: `src/components/gameplay/BusinessOperationsCard.tsx`

Variants:
- Margin outlook `favorable/mixed/pressured`
- Operated today `yes/no`
- Session `active/ended`
- Inventory `healthy/low/empty`

### 6) `StockMarketCard`
Source: `src/components/gameplay/StockMarketCard.tsx`

Variants:
- Quotes `available/unavailable`
- Holdings `has holdings/no holdings`
- Session `active/ended`
- Trade pending `buying/selling/idle`

### 7) Warning Banner
Mapped from real warning surfaces:
- `ErrorStateCard` warning surface pattern
- End-of-day warning box
- Inline fallback warning in gameplay page

Variants:
- Info
- Warning
- Danger
- Success

### 8) `EndOfDaySummaryCard`
Source: `src/components/gameplay/EndOfDaySummaryCard.tsx`

Variants:
- Guided day lesson `on/off`
- Tomorrow warnings `present/absent`
- Net `positive/negative`

## Part 3 - Main Gameplay Screen Mapping

Frame:
- iPhone portrait: `390 x 844`
- Safe area respected top and bottom

Locked structure mapping:
1. Top context: `Daily Brief`
2. Middle state: `Player Snapshot`
3. Bottom action zone: `ThumbReachActionDock` (persistent thumb zone) + `Action Hub` surface
4. Additional primary collapsibles: `Business Operations`, `Stock Market`, `Random Event` (when active)
5. Secondary collapsible groups under `Deep Dives`

Navigation anchors (mobile bottom nav):
- Brief
- Actions
- Progress
- Insights
- Account

## Part 4 - Onboarding Screens (Step 54 mapping)

Create 4 onboarding frames on `Onboarding` page:
1. Welcome screen (`welcome_core_premise`)
2. Daily Brief explanation (`read_todays_brief`)
3. Action explanation (`first_income_action`)
4. End day explanation (`end_first_day`)

Visual rules:
- Minimal copy
- Highlight target area only
- Keep the lower thumb zone emphasis

Onboarding component source:
- `src/components/gameplay/OnboardingBanner.tsx`

## Part 5 - First 3 Days Guided Flow Visuals

Create 3 guided storyboard frames:
1. Day 1: core loop (brief -> one action -> end day)
2. Day 2: pressure intro (bills/debt/recovery emphasis)
3. Day 3: opportunity intro (safe upside emphasis)

Data behavior source:
- Step 55 guided flow
- `OnboardingBanner` + guided end-of-day summary block

## Part 6 - Interaction States

Required state sets (component variants):
- Normal
- Pressed
- Disabled
- Loading
- Warning

Implemented mapping:
- Buttons: pressed scale and opacity, disabled opacity, loading spinner
- Trade buttons: tone-based variants + pressed/disabled
- Cards: warning/success/info surfaces using existing color contracts
- Loading state: compact/full skeleton card states
- Collapsibles: expanded/collapsed with show/hide affordance

## Part 7 - Mobile Frame Setup

Use:
- `390 x 844` portrait frame
- Safe area top + bottom
- Bottom action dock and bottom nav pinned within safe area handling
- No landscape variants

## Part 8 - Figma File Structure

Pages to create:
1. `Design System`
2. `Components`
3. `Gameplay Screens`
4. `Onboarding`
5. `States`

Recommended organization:
- Prefix components by domain (`GP/`, `UI/`, `LAYOUT/`)
- Use variant properties for state and tone
- Keep gameplay components tied to existing code names

## Part 9 - Validation Against Real App

Validation result:
- Matches current UI contract from code and Steps 58-60
- No invented gameplay modules added
- No layout contract changes introduced

Checklist pass:
- Top/middle/bottom gameplay hierarchy preserved
- Action dock remains thumb-first
- Business/stock cards remain collapsible primary surfaces
- Secondary groups remain demoted and collapsible
- Onboarding and guided day 1-3 flow represented

## Part 10 - Deliverable Summary

### Components Created (mapping set)
- DailyBriefCard
- PlayerStatsBar / Player Snapshot
- Action Button (Primary, Secondary)
- Bottom Action Bar + ThumbReachActionDock
- BusinessOperationsCard
- StockMarketCard
- Warning Banner
- EndOfDaySummaryCard

### Screens Created (mapping set)
- Gameplay main portrait screen
- Onboarding 4-step flow screens
- Guided Day 1, Day 2, Day 3 storyboard screens
- State gallery screens

### Design Tokens Defined
- Color, spacing, radius, elevation, typography from `src/design/tokens.ts`
- Gameplay semantic tones from active component styles

### Differences vs App
- No structural differences were introduced in this mapping.
- Operational gap only: Figma MCP is not authenticated in this runtime, so this output is a build-ready mapping spec rather than a directly generated Figma file.

### Future Improvements
- Connect Figma MCP and generate page/component nodes directly from this spec
- Add code-connect mapping between Figma components and `src/components/*`
- Add marketing-oriented presentation frames derived from Day 1-3 guided flow
- Add web-responsive companion frames after mobile parity is locked
