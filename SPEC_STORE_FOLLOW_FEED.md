# Store Follow Feed

**Status:** Draft — under discussion, nothing implemented yet
**Author:** Siddharth Gangadhar + Claude
**Date:** 2026-08-21
**Services affected:** groceror (backend), groceror-fe (frontend)

## 1. Background & Goal

Shoppers can already follow a store (`StoreFollow` / `api/store_follow_api.py`) and see the list of stores they follow on the `/following` page. Following does nothing beyond that today — it's not wired to anything a store does. Stores already have three separate ways to announce a deal (`Coupon`, `Promotion`, `FlashSale`), each with its own table and API, but none of them notify anyone; a shopper only sees a coupon/promo/flash sale if they happen to browse that store's page.

**Goal:** when a shopper follows a grocer, they should start seeing that store's activity — new coupons, promotions, flash sales, and free-text announcements — as a reverse-chronological **Feed** on the Following page, with an unread indicator. This is v1 — see **Out of Scope** for what's deliberately deferred.

## 2. Current State

| Piece | Status |
|---|---|
| Follow/unfollow a store, list followed stores | Exists — `StoreFollow`, `api/store_follow_api.py`, `/following` page |
| Coupons, Promotions, Flash Sales | Exist independently, no relation to `StoreFollow` — **Gap G1** |
| Any concept of a per-store activity log / feed item | **Gap G2** — doesn't exist |
| Notifying a follower that a followed store did something | **Gap G3** — doesn't exist in-app; no email/SMS fan-out either (out of scope for v1, see below) |
| Live in-app push infra | Exists — `api/sse_bus.py` + `/sse/stream`, already used for `order_status_update`, `new_order`, `delivery_status_update`, `low_stock_alert`, `back_in_stock` (see `client/src/hooks/use-sse.ts` in groceror-fe). Channel is keyed by a single user/store UUID — fan-out to N followers means one `publish()` call per follower, not a new mechanism. |
| Read/unread tracking anywhere in the app | **Gap G4** — no precedent; alerts (`PriceAlert`, `BackInStockAlert`) use `is_triggered`/`acknowledge`, not a cursor |

## 3. Proposed Design

### Feed source: hybrid (auto + manual)

A new `StoreFeedPost` table is the single source for feed items. Three of the existing store-side mutation handlers auto-insert a `StoreFeedPost` row as a side effect of what they already do; stores can additionally post free-text announcements directly.

| `update_type` | Emitted by | Trigger |
|---|---|---|
| `coupon` | `api/coupon_api.py::create_coupon` | every new coupon (not on deactivate) |
| `promotion` | `api/inventory_api.py::set_promotion` | only the **create** branch (`existing` is `None`) — an update to an existing promotion's price does not re-post, to avoid spamming the feed every time a store tweaks a price |
| `flash_sale` | `api/flash_sale_api.py::create_flash_sale` | every new flash sale |
| `announcement` | new endpoint, store-authored | manual, free text |

Cancelling/deactivating/deleting the underlying `Coupon`/`Promotion`/`FlashSale` does **not** touch its `StoreFeedPost` row — the feed is an immutable history log (like a social feed), not a live status mirror. This was chosen over sync-on-delete because it avoids wiring cleanup logic into three existing cancellation endpoints for a case (a shopper seeing an expired-looking feed item) that's cosmetic, not functional — the item's `created_at` already makes clear it's history.

A small shared helper avoids duplicating the insert/commit boilerplate across three call sites:

```python
# models/service/store_feed_service.py
def emit_update(store_id: UUID, update_type: str, message: str, ref_id: UUID | None = None) -> StoreFeedPost:
    update = StoreFeedPost(store_id=store_id, update_type=update_type, message=message, ref_id=ref_id)
    db_session.add(update)
    db_session.commit()
    db_session.refresh(update)
    _notify_followers(store_id, update)
    return update
```

`_notify_followers` looks up `StoreFollow.user_id` for the store and calls the existing `sse_publish(user_id, "store_update", {...})` once per follower — reusing the SSE bus already in place for order/stock notifications, not a new delivery mechanism. This keeps the feed "in-app only" (no email/SMS fan-out — see the Push delivery decision below) while still updating live for anyone with the app open, exactly like the existing `low_stock_alert`/`back_in_stock` events.

Auto-generated `message` text is built from data the handler already has:
- Coupon: `f"New coupon at {store.name}: {code} — {discount_value}% off"` (or `"$X off"` for `fixed`)
- Promotion: `f"{item.name} on sale for ${sale_price} through {end_date}"`
- Flash sale: `f"⚡ Flash sale: {item.name} now ${sale_price} until {end_at}"`

### Read tracking: global cursor

One `FeedReadState` row per user (`user_id` unique, `last_read_at`). Unread count = count of `StoreFeedPost` rows from followed stores where `created_at > last_read_at` (or all of them if the user has no `FeedReadState` row yet). A single cursor, not one per followed store — the badge is "you have N new updates," not per-store granularity. Marking read is an explicit action (`POST /feed/read`), not implicit on `GET /feed`, so opening the feed and closing it without scrolling doesn't silently clear a badge the user didn't actually see.

### Delivery: in-app only

No email/SMS fan-out to followers in v1 (per discussion — avoids deliverability/spam concerns for a store with many followers, and there's no per-follower opt-out mechanism to build alongside it). The SSE push above is still "in-app" — it only updates the badge/feed for a session that's already open, same tier as the existing order-status toasts.

## 4. Data Contracts

**`GET /feed`** (shopper, paginated, `limit` default 20 max 100, `offset` default 0)
```json
{
  "items": [
    {
      "id": "b3f1...",
      "store_id": "a1c2...",
      "store_name": "Fresh Mart",
      "update_type": "flash_sale",
      "message": "⚡ Flash sale: Organic Eggs now $3.99 until 5:00 PM",
      "ref_id": "d4e5...",
      "created_at": "2026-08-21T14:00:00Z"
    }
  ],
  "unread_count": 3,
  "has_more": true
}
```

**`POST /feed/read`** — no body, 204. Sets `FeedReadState.last_read_at = now()` for the caller (upsert).

**`POST /stores/updates`** (store, billing-gated like coupons — `_get_store_write`)
```json
// request
{ "message": "New shipment of organic produce arriving Friday!" }
// response: same shape as a feed item, update_type = "announcement", ref_id = null
```

**`DELETE /stores/updates/{update_id}`** (store, owner only) — 204. 400 if the target `update_type != "announcement"` (auto-generated entries aren't deletable through this endpoint — they're tied to their source record). 404 if not found or not owned by the caller's store.

**`GET /stores/{store_id}/updates`** (any authenticated user, paginated like `GET /feed`) — a single store's update history, for the store-browse page so a shopper can see recent activity before deciding to follow. Same item shape, no `unread_count`.

**SSE event** `store_update` on the existing `/sse/stream`, pushed to each follower's channel:
```json
{ "store_id": "a1c2...", "store_name": "Fresh Mart", "update_type": "flash_sale", "message": "⚡ Flash sale: ..." }
```

## 5. Required Changes

**Backend (`groceror`)**
- `models/entity/store_feed_post_entity.py` — new `StoreFeedPost` table (`id`, `store_id` FK, `update_type`, `message`, `ref_id` nullable UUID, `created_at`)
- `models/entity/feed_read_state_entity.py` — new `FeedReadState` table (`id`, `user_id` FK unique, `last_read_at`)
- `models/db.py` — add both new entity imports to the metadata-registration block (~line 40)
- New alembic migration adding `storefeedpost` and `feedreadstate` tables
- `models/service/store_feed_service.py` — new: `emit_update()`, `_notify_followers()`, list/pagination + unread-count query helpers shared by the router
- `api/store_feed_api.py` — new router: `GET /feed`, `POST /feed/read`, `POST /stores/updates`, `DELETE /stores/updates/{update_id}`, `GET /stores/{store_id}/updates`
- `main.py` — `from api.store_feed_api import store_feed_apis` + `app.include_router(store_feed_apis)`
- `api/coupon_api.py::create_coupon` — call `emit_update(...)` after the existing commit
- `api/inventory_api.py::set_promotion` — call `emit_update(...)` only in the `else` (create) branch; needs the `Inventory.name` already available via `item`
- `api/flash_sale_api.py::create_flash_sale` — call `emit_update(...)` after creation
- Tests: unit tests for `store_feed_service` (message building, unread-count math, pagination); integration tests for the new router (auth/ownership on delete, billing-lock on `POST /stores/updates`, pagination, `has_more`) and for auto-emission wired into the three existing create endpoints

**Frontend (`groceror-fe`)**
- `client/src/pages/following.tsx` — add a Feed section (tab or stacked list below the followed-stores list) rendering `GET /feed` items, calling `POST /feed/read` when the section is viewed
- `client/src/components/layout.tsx` — unread-count badge on the "Following" nav link (~lines 145, 230), sourced from the feed query's `unread_count`
- `client/src/hooks/use-sse.ts` — add a `store_update` listener alongside the existing ones: invalidate the feed query, show a toast (`New update from {store_name}`)
- `client/src/pages/dashboard.tsx` (store owner landing) — small composer to post an announcement (`POST /stores/updates`) + list of the store's own past updates with delete (only for `announcement` type)

## 6. Error Handling

- `GET /feed`, `POST /feed/read` require a shopper `User` profile — same 400 "User profile not set" pattern as `store_follow_api._get_user`
- `POST /stores/updates` requires a store profile and is billing-gated (402 if locked), matching `coupon_api._get_store_write`
- `DELETE /stores/updates/{update_id}`: 404 if missing or owned by a different store; 400 if `update_type != "announcement"`
- `limit` on paginated endpoints is clamped to `[1, 100]`, matching the existing clamping pattern in `test_revenue_trend_days_clamped_*`
- SSE fan-out failures are silent no-ops (existing `sse_publish` behavior when the event loop isn't running) — a missed live push just means the shopper sees the update on next `GET /feed` poll instead

## 7. Implementation Order

1. Backend: `StoreFeedPost` + `FeedReadState` entities, migration, `models/db.py` registration
2. Backend: `store_feed_service.py` (`emit_update`, `_notify_followers`, list/unread-count helpers) + unit tests
3. Backend: wire `emit_update()` into `create_coupon`, `set_promotion` (create branch only), `create_flash_sale` + integration tests confirming feed entries appear
4. Backend: `store_feed_api.py` router (all five endpoints) + `main.py` registration + integration tests
5. Frontend: Feed section on `following.tsx` + unread badge in `layout.tsx`
6. Frontend: `store_update` SSE listener in `use-sse.ts`
7. Frontend: announcement composer + own-updates list on `dashboard.tsx`
8. End-to-end check: follow a store, have it create a coupon/flash sale/manual post, confirm each shows in the feed, the badge increments, live SSE push updates an open session, and `POST /feed/read` clears the badge

## 8. Out of Scope (this version)

- Email/SMS fan-out to followers (in-app only for v1)
- Per-store unread badges (single global cursor per user)
- Editing a posted announcement (create/delete only)
- Rich content in announcements (images, links beyond the auto-populated `ref_id`)
- Muting a specific followed store's updates while remaining followed
- A public, non-authenticated version of `GET /stores/{store_id}/updates`
- Retention/archival policy for old `StoreFeedPost` rows (none — grows unbounded, same as `Coupon`/`FlashSale` today)
