# Saved Deals (My Deals)

**Status:** Draft — under discussion, nothing implemented yet
**Author:** Siddharth Gangadhar + Claude
**Date:** 2026-08-22
**Services affected:** groceror (backend), groceror-fe (frontend)

Entry point, per-type behavior, and the saved-list shape were decided in a scoping conversation preceding this document and are recorded here rather than relitigated in Proposed Design. This spec assumes those decisions and focuses on design.

## 1. Background & Goal

The store follow feed (`SPEC_STORE_FOLLOW_FEED.md`, shipped) shows a shopper reverse-chronological updates from stores they follow — including `coupon`, `promotion`, and `flash_sale` items. Today every feed item is inert text: there is nothing to click, and nothing that carries a coupon, promotion, or flash sale from the feed into anything durable on the shopper's account. A shopper who sees a coupon in their feed has to remember the code and go type it in at checkout later; a shopper who sees a flash sale has no way to flag "remind me, I want this" the way they already can for an ordinary product via the wishlist (`WishlistItem`).

**Goal:** let a shopper click a coupon/promotion/flash-sale item in their feed to save it to a personal **My Deals** list, so it's easy to find again later — without changing how a coupon is actually redeemed at checkout. This is v1 — see **Out of Scope**.

## 2. Current State

| Piece | Status |
|---|---|
| Feed items for `coupon`/`promotion`/`flash_sale` | Exist (`StoreFeedPost`, `GET /feed`) — plain text, not clickable, nothing persists a shopper's interest in one — **Gap G1** |
| Coupon redemption | Exists, code-entry only — `Order.coupon_code`, `coupon_api.py`'s `GET /coupons/{code}/validate`. No concept of a coupon being attached to a shopper's account; the shopper has to know/type the code. This spec does **not** change that — saving a coupon is a bookmark, not a checkout shortcut (decided in scoping) |
| Flash sale / promotion pricing | Automatic — `FlashSale.sale_price`/`Promotion.sale_price` already apply to the product's shown price with no shopper action needed. There's nothing to "redeem"; the gap is purely "I want to be able to find this again before it ends" |
| "Save this for later" pattern | Exists for products — `WishlistItem` (`user_id`, `inventory_id`, unique pair), `wishlist_api.py`'s add/list/check/remove shape. This is the precedent to mirror, not reuse directly (a deal isn't an `Inventory` row, it's a `StoreFeedPost`) |
| Expiry-aware state | Exists as raw fields (`Coupon.valid_until`/`max_uses`+`is_active`, `Promotion.end_date`, `FlashSale.end_at`+`is_active`) but nothing today reads them to produce a shopper-facing "is this still good" status |
| `StoreFeedPost` mutability | Immutable log (`SPEC_STORE_FOLLOW_FEED.md` §3) — a feed post is never deleted or edited even after its underlying coupon/flash sale ends. A saved deal must compute freshness from the *underlying* `Coupon`/`Promotion`/`FlashSale` row at read time, not assume the feed post itself reflects current status |

## 3. Proposed Design

### 3.1 One save action, one new table

A single `SavedDeal` row represents "this shopper bookmarked this feed item" — it references the `StoreFeedPost`, not the underlying `Coupon`/`Promotion`/`FlashSale` directly, since the feed post is what the shopper actually clicked on and already carries `update_type`/`ref_id`/`store_id`.

```python
class SavedDeal(SQLModel, table=True):
    __tablename__ = "saveddeal"
    __table_args__ = (UniqueConstraint("user_id", "feed_post_id", name="uq_saveddeal_user_feedpost"),)

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)
    feed_post_id: UUID = Field(foreign_key="storefeedpost.id", index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
```

Only `StoreFeedPost` rows with `update_type` in `{"coupon", "promotion", "flash_sale"}` are saveable — `announcement` (free text, no discount to track) is rejected with a 400, same posture as `DELETE /stores/updates/{id}` rejecting non-`announcement` types today for the opposite reason.

### 3.2 Computing freshness at read time

Because the feed post is immutable but the underlying deal isn't, `GET /my-deals` resolves each saved row's `update_type`/`ref_id` back to its source (`Coupon`, `Promotion`, or `FlashSale`) and computes a `status` the same way each existing read path already determines validity — no new business rule, just reused in one more place:

| `update_type` | Source lookup | `upcoming` | `active` | `expired` |
|---|---|---|---|---|
| `coupon` | `Coupon` by `ref_id` | `valid_from` is future | `is_active`, within `valid_from`/`valid_until`, under `max_uses` (same check as `validate_coupon`) | `is_active == False`, past `valid_until`, or `max_uses` reached |
| `promotion` | `Promotion` by `ref_id` | `start_date` is future | within `start_date`/`end_date` | past `end_date` |
| `flash_sale` | `FlashSale` by `ref_id` | `now < start_at` | `is_active`, within `start_at`/`end_at` | `is_active == False` or `now > end_at` |

If the source row can't be found at all (hard-deleted — not expected in practice, since none of the three are ever hard-deleted today, only deactivated), the saved row is silently excluded from the response, matching `wishlist_api.py::_enrich`'s existing "skip if the referenced thing is gone" behavior.

Expired deals are **not** removed from `My Deals` — they stay, marked `expired`, so a shopper can see "I meant to use this and missed it" rather than it silently vanishing. No cleanup job is needed for the same reason `subscription_service` avoids one: this is computed lazily on every read, not tracked by a background process.

### 3.3 List ordering

`GET /my-deals` sorts `active`/`upcoming` deals first (soonest-expiring first — the ones most worth acting on), then `expired` deals last (most-recently-expired first). This is a presentation decision the endpoint itself makes (a single `ORDER BY` expression over the computed status+expiry), not something the frontend needs to re-derive.

## 4. Data Contracts

```json
// POST /feed/{feed_post_id}/save  →  response (shopper)
{
  "id": "9f1a...",
  "feed_post_id": "b3f1...",
  "update_type": "coupon",
  "store_id": "a1c2...",
  "store_name": "Fresh Mart",
  "message": "New coupon at Fresh Mart: SAVE10 — 10% off",
  "status": "active",              // upcoming | active | expired
  "expires_at": "2026-09-01T00:00:00Z",   // null if the source has no end date
  "code": "SAVE10",                // present only for update_type == "coupon"
  "sale_price": null,              // present only for promotion / flash_sale
  "saved_at": "2026-08-22T10:00:00Z"
}
// 400 if the target StoreFeedPost's update_type isn't coupon/promotion/flash_sale
// 404 if the feed post doesn't exist
// Idempotent — saving an already-saved post returns the existing row, mirrors POST /wishlist

// DELETE /feed/{feed_post_id}/save  →  204 (shopper, no-op if not saved)

// GET /feed/{feed_post_id}/saved  →  response (shopper)
true

// GET /my-deals  →  response (shopper)
{
  "items": [ /* same shape as POST /feed/{id}/save's response, one per saved deal */ ]
}
```

## 5. Required Changes

**Backend (`groceror`)**
- `models/entity/saved_deal_entity.py` — new `SavedDeal` (§3.1)
- `models/db.py` — register the new entity
- New alembic migration (down_revision the current head) adding the `saveddeal` table
- New `models/service/saved_deal_service.py` — `save(user_id, feed_post_id)`, `unsave(user_id, feed_post_id)`, `is_saved(user_id, feed_post_id)`, `list_for_user(user_id)` (resolves each row to its source per §3.2, computes `status`, sorts per §3.3)
- New `api/saved_deal_api.py` — `POST /feed/{feed_post_id}/save`, `DELETE /feed/{feed_post_id}/save`, `GET /feed/{feed_post_id}/saved`, `GET /my-deals`
- `main.py` — register the new router
- Tests: unit tests for `saved_deal_service` (status computation for all three types × upcoming/active/expired, ordering, idempotent save, missing-source row excluded); integration tests for the router (400 on `announcement`, 404 on missing post, idempotent save, unsave, `GET /my-deals` shape and ordering)

**Frontend (`groceror-fe`)**
- `client/src/pages/following.tsx` — feed items with `update_type` in `coupon`/`promotion`/`flash_sale` get a bookmark/save toggle (filled state driven by `GET /feed/{id}/saved`, or by items already known to be saved from a bulk `GET /my-deals` fetch)
- New `client/src/pages/my-deals.tsx` — the unified saved-deals list: each row shows store, message, status badge (`upcoming`/`active`/`expired`), and a type-appropriate action — a copyable coupon code for `coupon`, a "View item" link to the product for `promotion`/`flash_sale`
- `client/src/components/layout.tsx` — nav entry to `/my-deals` (alongside the existing Wishlist/Following links)
- `client/src/types/models.ts` — add a `SavedDeal` type

## 6. Error Handling

- `POST /feed/{feed_post_id}/save`: 404 if the feed post doesn't exist; 400 if its `update_type` isn't `coupon`/`promotion`/`flash_sale`; saving an already-saved post is a no-op that returns the existing row (not a 409) — matches `wishlist_api.py`'s existing idempotency posture
- `DELETE /feed/{feed_post_id}/save`: always 204, whether or not it was saved — matches `wishlist_api.py::remove_from_wishlist`'s silent-no-op behavior
- `GET /my-deals` requires a shopper `User` profile — same 400 "User profile not set" pattern used everywhere else in this codebase
- A saved deal whose source row can no longer be resolved is silently dropped from `GET /my-deals`, never a 500

## 7. Implementation Order

1. Backend: `SavedDeal` entity + migration + `models/db.py` registration
2. Backend: `saved_deal_service.py` (status computation for all three source types, ordering) + unit tests
3. Backend: `saved_deal_api.py` router + `main.py` registration + integration tests
4. Frontend: save/unsave toggle on `following.tsx` feed items
5. Frontend: `my-deals.tsx` page + nav link
6. End-to-end check: save a coupon, a promotion, and a flash sale from the feed; confirm all three show correctly in `My Deals` with the right status; let a flash sale's `end_at` pass and confirm it flips to `expired` without disappearing; confirm saving an `announcement` post is rejected

## 8. Out of Scope (this version)

- Auto-applying a saved coupon at checkout, or any change to how coupons are redeemed — saving is a bookmark only, per the scoping decision; the shopper still types the code
- Push/email/SMS reminders as a saved deal approaches expiry — `status` is computed and shown whenever the shopper opens `My Deals`, there's no proactive notification
- Saving from anywhere other than the feed (e.g. a "save" button on a store's own coupon-listing page) — feed-only for v1, per the scoping decision
- Stock reservation or any hold against a flash sale's inventory when saved — saving carries no purchasing guarantee
- Folding saved deals into the existing `Wishlist` page/table — kept as a separate `My Deals` list, since a deal isn't a product
- Sharing a saved deal with another shopper
- Any interaction with the (separately proposed, not yet built) Sponsored Posts feature — sponsored feed items use `update_type == "sponsored"`, which is deliberately not in the saveable set here
