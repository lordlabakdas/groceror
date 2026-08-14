# Rewards Program

**Status:** Draft — under discussion, nothing implemented yet
**Author:** Siddharth Gangadhar + Claude
**Date:** 2026-08-13
**Services affected:** groceror (backend), groceror-fe (frontend)

## 1. Background & Goal

The app already has a basic points ledger (`LoyaltyAccount` / `LoyaltyTransaction`, see `models/service/orders_service.py`): shoppers earn 1 point per $1 spent and redeem 100 points = $1 off at checkout. There are no tiers, no perks, and no distinction between "loyalty" (the ledger mechanic) and a "rewards program" (a reason to keep spending). The README lists "rewards programs" as an aspirational goal; nothing beyond the point ledger exists today.

**Goal:** add spending tiers on top of the existing point ledger. Higher lifetime spend unlocks a faster point-earning rate, giving shoppers a visible reason to consolidate spend on the platform. This is v1 — see **Out of Scope** for what's deliberately deferred.

## 2. Current State

| Piece | Status |
|---|---|
| Points ledger (earn/redeem) | Exists — `orders_service.py`, `LoyaltyAccount`, `LoyaltyTransaction` |
| `GET /loyalty/balance`, `GET /loyalty/history` | Exist — `api/loyalty_api.py`, read-only |
| Tiers | **Gap G1** — no concept of tier anywhere |
| Lifetime-spend tracking | **Gap G2** — no cached counter on `User`; would need a live query over `Order` |
| Tier-aware point earning | **Gap G3** — `POINTS_PER_DOLLAR` (`orders_service.py`) is a flat constant, same for everyone |
| Frontend tier display | **Gap G4** — `loyalty.tsx` shows balance/history only, no tier/progress UI |

## 3. Proposed Design

### Tier model

Three tiers, gated on **lifetime spend** — the sum of `total_price` across all of a shopper's non-cancelled orders, computed live from the `Order` table (no cached counter; order volume doesn't justify the sync-drift risk of a denormalized column yet).

| Tier | Lifetime spend threshold | Points multiplier |
|---|---|---|
| Bronze | $0 (default) | 1.0× |
| Silver | $250+ | 1.25× |
| Gold | $750+ | 1.5× |

Tiers only ever go up — lifetime spend is cumulative and never decreases, so there's no downgrade path to handle (this was chosen explicitly over a rolling-12-month model to avoid the added complexity of a re-evaluation job).

Thresholds and multipliers are hardcoded constants (matching how `POINTS_PER_DOLLAR` / `POINTS_PER_DOLLAR_REDEMPTION` already work), not a DB-editable table — there's no per-store customization requirement, so a code change + deploy to adjust tiers is an acceptable tradeoff for v1's simplicity.

### Earning rule

A shopper's tier for a given order is computed from their lifetime spend **excluding** the order currently being placed (i.e., spend from all *prior* completed orders). That tier's multiplier applies to the points earned on the current order. This avoids a circular "this order's spend determines this order's own multiplier" ambiguity. Concretely: `points_earned = floor(total_price * POINTS_PER_DOLLAR * tier_multiplier(prior_lifetime_spend))`.

### Where it's computed

New helper in `models/service/orders_service.py` (alongside the existing `_get_or_create_loyalty_account`): `_get_tier(user_id) -> Tier`, querying `sum(Order.total_price) where user_id = ... and status != 'cancelled'`, mapping to a tier via the threshold table above. Called from `create_order()` right before the points-earning step (currently `orders_service.py:165`).

## 4. Data Contracts

`GET /loyalty/balance` response gets three new fields (no new endpoint — same call the frontend already makes):

```json
{
  "points_balance": 340,
  "total_earned": 500,
  "total_redeemed": 160,
  "dollar_value": 3.40,
  "tier": "silver",
  "multiplier": 1.25,
  "next_tier": "gold",
  "spend_to_next_tier": 210.00
}
```

`next_tier` / `spend_to_next_tier` are `null` when already at the top tier (Gold).

## 5. Required Changes

**Backend (`groceror`)**
- `models/service/orders_service.py`: add tier constants + `_get_tier()` helper; apply multiplier in the points-earning step
- `api/loyalty_api.py`: extend `GET /loyalty/balance` handler to compute and include tier fields
- `api/validators/` (loyalty validator file): extend the balance response model with the new fields
- Tests: unit tests for `_get_tier()` at each threshold boundary; integration test confirming a Silver/Gold shopper's order earns the multiplied point amount

**Frontend (`groceror-fe`)**
- `client/src/pages/loyalty.tsx`: add a tier badge, a progress bar toward the next tier (using `spend_to_next_tier`), and an explanation of the current multiplier
- `client/src/types/models.ts`: extend the loyalty balance type with the new fields

## 6. Error Handling

No new failure modes beyond what `GET /loyalty/balance` already has (auth-required 401). Tier computation is a pure read — if the underlying `sum()` query returns `None` (no orders yet), treat as $0 lifetime spend → Bronze.

## 7. Implementation Order

1. Backend: tier constants + `_get_tier()` helper + unit tests
2. Backend: wire multiplier into `create_order()` points-earning step + integration test
3. Backend: extend `GET /loyalty/balance` response + validator
4. Frontend: tier badge + progress bar on `loyalty.tsx`
5. End-to-end check: seed/place orders crossing a threshold, confirm multiplier and displayed tier both update correctly

## 8. Out of Scope (this version)

- Free delivery perk — no delivery-fee system exists yet; deferred until that's built
- Early access to flash sales — needs a schema change (`FlashSale.early_access_at` or similar) plus tier-gating in `flash_sale_api.py`
- Rewards catalog (redeem points for specific items/perks instead of $ off)
- Tier downgrade / rolling-window spend evaluation
- Store-specific rewards programs (this is platform-wide, shoppers only)
- Referral bonuses, birthday bonuses, streaks/challenges
