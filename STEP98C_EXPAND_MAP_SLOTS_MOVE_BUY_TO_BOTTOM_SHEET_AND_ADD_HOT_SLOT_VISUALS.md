# STEP 98C — Expand Map Slots, Move Buy To Bottom Sheet, Add Hot Slot Visuals

## Summary

The map interaction is now slot-detail driven:

Browse map → tap slot → selected slot sheet opens → inspect land/business state → buy/build/run/manage from the sheet.

The map surface no longer shows direct `Buy` controls on every lot tile.

## Map Slot Expansion

Unlocked purchasable lot capacity increased from 16 lots to 59 lots.

- Suburban Area expanded from 8 to 17 purchasable lots with more side-street, gateway, infill, and park-front parcels.
- Downtown City expanded from 8 to 18 purchasable lots with more infill, station frontage, waterfront, service-flex, and premium commercial parcels.
- Riverside Grove is now an unlocked open expansion area with 12 purchasable lots, including cheaper rural-adjacent parcels and a few premium waterfront slots.
- Harbor Works is now an unlocked service/logistics expansion area with 12 purchasable lots across cheaper yards, service-flex pads, and hot shift-change sites.

## Bottom Sheet Buy Flow

The selected-slot detail card now acts as the interaction sheet.

- Unowned lot: shows land stats and `Buy Lot`.
- Owned empty lot: shows owned land state and `Build Here: Place ...`.
- Owned built site: shows business state, `Run Business`, `Restock Inventory`, and manage/advance action.
- Locked/service/special nodes: show status chips and descriptive copy/actions without purchase controls.

## Hot Slot System

Hot/strong slots are computed from:

- traffic score
- development potential
- district kind
- commercial/logistics/mixed-use zone value
- frontage/corner/gateway/waterfront/station keywords
- lot size

Visual treatment:

- Hot slots get a warmer gold/cyan-accent treatment, stronger border, and small premium spark.
- Strong slots get a quieter info-accent border/background.
- Normal slots stay subdued so the larger map does not become noisy.

## Status Handling

Every selected cell resolves to clear status language:

- `Buyable`
- `Hot Slot`
- `Owned`
- `Active Site`
- `Locked`
- `Service Building`
- `Special Node`

For land lots, the sheet also separates `Land ownership` from `Business state` so it is clear whether the player owns land, has placed a business, or can run/manage a built site.

## Performance Notes

- The grid still uses lightweight pressable tiles.
- Tile labels are intentionally minimal after expansion.
- Slot rendering is moved into a memoized `DistrictGridCell` component.
- The selected sheet handles richer text/actions so the grid can scale without clutter.

## Files Changed

- `expo/src/features/gameplayLoop/screens/MapDashboardScreen.tsx`
- `STEP98C_EXPAND_MAP_SLOTS_MOVE_BUY_TO_BOTTOM_SHEET_AND_ADD_HOT_SLOT_VISUALS.md`

## Before / After UX

Before:

- Only two unlocked areas with 16 total purchasable lots.
- Unowned lot tiles displayed direct `Buy` language and prices across the grid.
- Premium slots did not stand out clearly.
- Owned land and built business state were easy to confuse.

After:

- Four unlocked areas with 59 purchasable lots.
- Lot tiles show compact status/opportunity information only.
- Buy/build/run/manage actions live in the selected-slot sheet.
- Hot and strong lots are visually distinct without overloading the map.
- Owned empty land and active built sites have separate, clearer action flows.

## Validation

- `yarn typecheck` passed.
- UI color audit passed through the typecheck script.
- Manual code-path validation confirmed buy buttons now render only in the selected-slot sheet, not on map grid tiles.
