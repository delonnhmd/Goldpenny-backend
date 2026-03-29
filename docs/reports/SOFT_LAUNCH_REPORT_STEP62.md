# Soft Launch Report - Step 62

## Objective
Release Gold Penny to a small real-user cohort, observe first-session behavior, and identify high-impact UX friction in the first-day gameplay loop.

## Scope and Constraints
- Core logic remains frozen (Step 57).
- UI structure remains locked (Step 58).
- Visual polish baseline from Steps 59-60 is preserved.
- Design-system baseline from Step 61 is used as the UI contract.

## Figma MCP Inspection Status
- Figma MCP authentication is active in this environment (`mcp__figma__whoami` successful).
- The project repo does not contain a target Figma file URL/node-id for Gold Penny Step 62.
- Direct node-level `get_design_context`/`get_screenshot` for the Gold Penny design could not be completed without a shared target node.

Design baseline used for Step 62 UI decisions:
- `FIGMA_DESIGN_SYSTEM_REPORT_STEP61.md`
- `src/pages/gameplay/GameDashboardPage.tsx`
- `src/components/gameplay/DailyBriefCard.tsx`
- `src/components/gameplay/PlayerStatsBar.tsx`
- `src/components/gameplay/ActionHubPanel.tsx`
- `src/components/gameplay/ThumbReachActionDock.tsx`
- `src/components/gameplay/OnboardingBanner.tsx`
- `src/components/gameplay/BusinessOperationsCard.tsx`
- `src/components/gameplay/StockMarketCard.tsx`
- `src/components/gameplay/EndOfDaySummaryCard.tsx`

## Soft Launch Plan

### 1. User Profiles (Target 10 Testers)
- 6 non-technical users unfamiliar with Gold Penny-style economy loops
- 2 users who play mobile sim/strategy games but are new to this app
- 2 users with finance/economy familiarity

Recruitment constraints:
- No prior walkthrough from the team
- Mix of ages/devices where possible
- At least 50% should be first-time players to this genre

### 2. Test Instructions Given to Users
Use this exact script:
1. Install the app.
2. Open it and start playing.
3. Do not ask for help unless you are fully stuck.

Moderator rule:
- Observe silently for first 2 minutes.
- Do not explain UI labels, game rules, or strategy.

## Observation Framework

### 3. First 2 Minutes (Critical)
Track per tester:
- First tap target (onboarding button, brief, dock, random section)
- Time-to-first-action (seconds)
- Hesitation points (>5 seconds idle)
- Mis-taps or loops (open/close sections repeatedly)
- Whether user notices bottom dock actions without prompting

### 4. First Session Completion Checks
For each tester, record:
- Completed Day 1: Yes/No
- Understood "Daily Brief": Yes/Partially/No
- Knew what to do next after first action: Yes/No
- Found and used "End Day": Yes/No
- Reached End-of-Day Summary: Yes/No

## Post-Session Interview Prompts
Ask only:
- What confused you?
- What did you not understand?
- What did you like?
- What felt hard?
- Would you play again?

## Issue Taxonomy
Classify each issue into one primary bucket:
- UX confusion
- unclear wording
- poor feedback
- pacing issues
- balance issues
- interaction friction

Severity rubric:
- P0: blocks first-day completion
- P1: causes wrong actions, repeated hesitation, or abandonment risk
- P2: noticeable but recoverable confusion
- P3: cosmetic or preference-only

## Observed Behaviors (Step 62 Pre-Launch Risk Pass)
Note: Live external-user observations are pending; items below are risk hotspots derived from the locked UI flow.

- Players are likely to split attention between `Daily Brief` and `Action Hub`, delaying first action if the dock is not treated as primary.
- "Time units" language may be unclear for new users in the first 60 seconds.
- Users may preview actions in the hub but still miss the required `End Day` step.
- Collapsible sections can invite exploration before completing the core loop.

## Major Issues Found (Pre-Launch High-Impact Queue)

1. First-action ambiguity in first 60 seconds
- Category: UX confusion
- Severity: P1
- Evidence source: current first-screen hierarchy and copy in `DailyBriefCard`, `ActionHubPanel`, and dock

2. "Units left" mental model unclear
- Category: unclear wording
- Severity: P1
- Evidence source: dock summary text and session tempo wording

3. End-day action can be discovered late after one action
- Category: interaction friction
- Severity: P1
- Evidence source: dock flow and mixed emphasis between "Work" and "End Day"

4. Preview-vs-execute distinction is not always obvious to new users
- Category: poor feedback
- Severity: P2
- Evidence source: action-card preview path and section density

## Implementable UI Decisions (From Design Baseline)
These are execution-ready once validated by Cycle 1 observation data.

1. Make first-loop language explicit in the dock
- Proposed copy change: "X/Y time units left today"
- Expected impact: faster comprehension of session budget

2. Add a persistent first-day hint until first action is completed
- Proposed hint: "Tap Work, then End Day"
- Placement: dock hint area / onboarding banner hint line
- Expected impact: reduce first-action indecision

3. Strengthen End Day affordance after first action completes
- Trigger: when at least one core action is logged
- Expected impact: improve Day 1 completion rate

4. Add explicit blocked-action reason in hub cards
- Example: "Needs more time units" / "Session already ended"
- Expected impact: reduce trial-and-error tapping

5. Keep deep-dive sections visually secondary during first-day guided state
- Preserve current structure; tighten attention to Brief -> Dock -> End Day path
- Expected impact: less early-session distraction

## Fixes Applied in Step 62
- Operational fix: Created a strict no-guidance observation protocol.
- Process fix: Added a severity taxonomy and P0/P1-only launch-fix rule.
- Prioritization fix: Established first-60-seconds decision criteria for immediate UI updates.

No gameplay-logic or production UI code changes were applied in this report-only step.

## Iteration Loop (2-3 Cycles)

### Cycle 1
- Run 5 users
- Fix only P0/P1 issues
- Re-test with 3 new users

### Cycle 2
- Run 5 additional users
- Validate previous fixes
- Address any remaining P1 friction in first-day flow

### Cycle 3 (Optional)
- Run 3-5 users
- Confirm no major Day 1 blockers
- Capture retention intent and confidence signal

## Retention Signals to Track
Primary:
- Day 1 completion rate
- "Would play again" yes-rate
- % users who complete first loop without moderator help

Secondary:
- Time-to-first-action
- Time-to-End-Day
- Number of hesitation points in first 2 minutes
- Number of users who revisit app within 24-48 hours (if measurable)

## Next Improvements (Post-Cycle Priorities)
1. Clarify first-loop language and action ordering in the dock.
2. Tighten onboarding microcopy around Daily Brief interpretation.
3. Improve immediate feedback when actions are blocked or preview-only.
4. Reduce cognitive load in first session by suppressing low-priority exploration prompts.
5. Add lightweight analytics events for first-action, first-hub-open, and end-day taps.

## Success Criteria Check
- Users understand what to do without help: target >= 80%
- Users complete first day: target >= 85%
- No major confusion blocks progress: 0 unresolved P0s
- Users show interest in continuing: target >= 60% "would play again"

## Deliverable
`SOFT_LAUNCH_REPORT_STEP62.md` created with:
- user profiles
- observed behavior framework + risk hotspots
- major issues queue
- fixes applied (process-level)
- retention signals
- next improvements
