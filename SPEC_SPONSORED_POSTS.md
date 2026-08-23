# Sponsored Posts

**Status:** Draft — under discussion, nothing implemented yet
**Author:** Siddharth Gangadhar + Claude
**Date:** 2026-08-22
**Services affected:** groceror (backend), groceror-fe (frontend)

Payment shape, pricing model, post lifetime, and feed placement were decided in a scoping conversation preceding this document and are recorded here rather than relitigated in Proposed Design. This spec assumes those decisions and focuses on design.

## 1. Background & Goal

The store follow feed (`SPEC_STORE_FOLLOW_FEED.md`, shipped in PR #66) shows a shopper reverse-chronological activity — coupons, promotions, flash sales, announcements — from stores they follow, via `StoreFeedPost` rows and `GET /feed`. It is strictly opt-in: `store_feed_service.list_feed()` filters to `StoreFeedPost.store_id IN (stores the user follows)`. A store with zero followers reaches zero shoppers through it.

**Goal:** let any store pay a nominal one-time fee to publish a free-text post that appears in **every** shopper's feed, regardless of follow status — a paid broadcast slot layered on top of the existing organic feed. This is v1 — see **Out of Scope** for what's deliberately deferred.

Decided shape (this scoping conversation):
- **Payment: pay-per-post**, a one-time Razorpay charge at post-creation time. No prepaid credit/wallet concept — the post goes live once that one payment confirms.
- **Pricing: a single flat fee**, admin-configurable (mirrors `SubscriptionPlan`'s pattern in `SPEC_SUBSCRIPTION.md` §3.1) — not a hardcoded constant, so the platform owner can change it without a deploy.
- **Post lifetime: forever**, same immutable-log treatment as every other `StoreFeedPost` entry — no expiry, no separate "boost window." Once paid and posted, it's permanent feed history exactly like a coupon or flash-sale entry.
- **Placement: interleaved by `created_at`**, in the same single reverse-chronological list as organic updates — no pinning, no dedicated slots. Visually distinguished by `update_type` alone.

**Proposed default (confirm before implementation, easy to change — it's a constant seed value, not schema):**

| Constant | Proposed value |
|---|---|
| Sponsored post fee | ₹199/post (initial value — thereafter admin-editable, §3.4) |

## 2. Current State

| Piece | Status |
|---|---|
| `StoreFeedPost` table, `emit_update()`, `GET /feed`, `GET /stores/{id}/updates` | Exists (`models/service/store_feed_service.py`, `api/store_feed_api.py`) — single source for feed items, four `update_type`s today: `coupon`, `promotion`, `flash_sale`, `announcement` |
| `GET /feed` scope | Follower-only — **Gap G1**. `list_feed`/`count_feed`/`unread_count` all filter `StoreFeedPost.store_id IN (SELECT store_id FROM StoreFollow WHERE user_id = ...)`. No mechanism to reach a non-follower at all. |
| Razorpay integration | Exists, but **subscriptions only** — **Gap G2**. `engine/billing/provider.py`'s `BillingProvider` Protocol has `create_plan`/`create_customer`/`create_subscription`/`cancel_subscription`, all recurring-billing shaped. Nothing creates a one-time Razorpay `Order` or verifies a one-time payment signature. |
| Admin-configurable pricing | Exists as a pattern — `SubscriptionPlan` (append-only price history, `subscription_service.set_plan_price`/`get_current_plan`) is the precedent to mirror, not reuse directly (it's monthly-plan shaped, sponsored posts need a flat one-time price). |
| Billing-lock gating on store mutations | Exists — `subscription_service.assert_billing_ok(store)`, called from each router's local `_get_store_write()` (e.g. `store_feed_api.py:36-39`). A `locked` store already can't post an announcement or create a coupon. |
| Admin auth | Exists — `_require_admin` (`X-Admin-Token` header, `AdminConfig.ADMIN_TOKEN`), reused as-is (§3.4). |

## 3. Proposed Design

### 3.1 New entities

```python
class SponsoredPostPricing(SQLModel, table=True):
    """Append-only price history for the flat per-post fee, same shape and
    rationale as SubscriptionPlan (SPEC_SUBSCRIPTION.md §3.1): the current
    price is the most recent row; never mutated in place, so a price change
    doesn't touch any SponsoredPost already created and leaves a free audit
    trail of what Groceror charged and when."""
    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    price_paise: int                                # e.g. 19900 = ₹199.00
    created_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: str = Field(default="admin")        # informational only — X-Admin-Token has no identity

class SponsoredPost(SQLModel, table=True):
    """One row per paid broadcast attempt — created in status="pending" at
    checkout time, before any money has moved. Snapshots the price actually
    charged, same rationale as Subscription.plan_price_paise: a later admin
    price change must not retroactively alter what an already-created (or
    already-paid) post cost."""
    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    store_id: UUID = Field(foreign_key="store.id", index=True)
    message: str
    amount_paise: int                               # snapshotted SponsoredPostPricing price at checkout
    status: str = Field(default="pending", index=True)  # pending / paid / failed
    razorpay_order_id: Optional[str] = None
    razorpay_payment_id: Optional[str] = None
    feed_post_id: Optional[UUID] = None              # set to the resulting StoreFeedPost.id once paid
    created_at: datetime = Field(default_factory=datetime.utcnow)
    paid_at: Optional[datetime] = None
```

Both must be added to `models/db.py`'s explicit entity-import block or their tables silently won't exist under test (per the "Testing Approach" section of `CLAUDE.md`).

**Why a separate `SponsoredPost` table rather than cramming payment fields onto `StoreFeedPost`:** `StoreFeedPost` is a lightweight, uniform "what happened" log across four (soon five) event types — none of the other four carry payment state. A `pending` sponsored post (payment not yet confirmed) must **not** appear in anyone's feed, which means it can't be a `StoreFeedPost` row yet; a `SponsoredPost` row is the natural place to track that pre-payment state; the `StoreFeedPost` row (via `emit_update`, same as the other three auto-emitted types) only gets created at the moment payment is confirmed (§3.3).

### 3.2 Broadening `GET /feed` to non-followers

`update_type = "sponsored"` is added to `store_feed_service.UPDATE_TYPES`. The three feed-query helpers change their filter from "followed stores only" to "followed stores, **or** any sponsored post":

```python
def _feed_scope_filter(user_id: UUID):
    followed = select(StoreFollow.store_id).where(StoreFollow.user_id == user_id)
    return or_(StoreFeedPost.store_id.in_(followed), StoreFeedPost.update_type == "sponsored")
```

`list_feed`, `count_feed`, and `unread_count` each swap their existing `.where(StoreFeedPost.store_id.in_(...))` clause for `.where(_feed_scope_filter(user_id))`. This is the entire mechanism for "reaches all shoppers" — no per-user fan-out insert, no broadcast job; a sponsored post is just one `StoreFeedPost` row that the OR-clause makes visible to every shopper's `GET /feed` query, the same way a single `Coupon` row is visible to every follower's query today. Ordering, pagination (`limit`/`offset`/`has_more`), and the unread cursor (`FeedReadState`) all continue to work unmodified — a sponsored post is just another row sorted by `created_at`, per the interleaved-placement decision.

`GET /stores/{store_id}/updates` needs no change — it already returns all `StoreFeedPost` rows for a store_id regardless of type, so a store's own sponsored posts show up in its public activity history alongside its coupons/flash sales, which is the correct behavior (a shopper browsing the store page before following can see it ran a sponsored post).

`DELETE /stores/updates/{update_id}` needs no change either — its existing guard (`update_type != "announcement"` → 400) already refuses to delete anything but manual announcements, so it naturally refuses to delete a `sponsored` row too. A paid post is not cancellable/refundable in v1 (see Out of Scope), consistent with the immutable-log, no-expiry decision.

The `store_update` SSE event (fanned out via `_notify_followers`, unchanged) still only reaches the store's **followers** in real time — a non-follower only sees a new sponsored post on their next `GET /feed` poll, not instantly. Widening SSE fan-out to literally every connected shopper is a bigger change (§8, Out of Scope) that isn't required by the "appears in the feed" goal.

### 3.3 Payment flow (Razorpay one-time Order)

**Everything about the Razorpay Orders API call shapes below is the assumed shape from general knowledge, not verified against current Razorpay docs or a real account — same posture `SPEC_SUBSCRIPTION.md` §3.4 took for Subscriptions, and `SPEC_DELIVERY_DISPATCH.md` took for Shiprocket Quick. Confirming this shape against a real test account is an implementation-order item (§7), not assumed away.**

`BillingProvider` (`engine/billing/provider.py`) gains two methods, implemented in `RazorpayProvider` and `FakeBillingProvider` alongside the existing subscription methods:

```python
@dataclass
class RazorpayOrder:
    razorpay_order_id: str

class BillingProvider(Protocol):
    ...
    def create_order(self, amount_paise: int) -> RazorpayOrder:
        """One-time charge — Razorpay Orders API, distinct from the
        Subscriptions objects above. currency="INR"."""
        ...

    def verify_payment_signature(self, order_id: str, payment_id: str, signature: str) -> bool:
        """Synchronous verification of a client-side Razorpay Checkout
        success callback — razorpay.utility.verify_payment_signature,
        HMAC-SHA256 over order_id|payment_id keyed by KEY_SECRET. Distinct
        from verify_webhook_signature, which validates an inbound webhook
        POST, not a checkout-handler callback."""
        ...
```

Flow:

1. `POST /stores/sponsored-posts` (store, billing-gated same as `POST /stores/updates` — a `locked` store can't buy a sponsored slot either): resolves the current `SponsoredPostPricing` price, calls `provider.create_order(price.price_paise)`, creates a `SponsoredPost` row (`status="pending"`, `amount_paise` snapshotted, `razorpay_order_id` set). Returns `{sponsored_post_id, razorpay_order_id, amount_paise, razorpay_key_id}` for the frontend's Razorpay Checkout widget (Orders mode, not Subscriptions mode — a different Checkout invocation shape client-side).
2. Frontend opens Razorpay Checkout with that `order_id`; on success the client-side handler receives `razorpay_payment_id`, `razorpay_order_id`, `razorpay_signature`.
3. `POST /stores/sponsored-posts/{id}/confirm` (store, must own the `SponsoredPost`), body `{razorpay_payment_id, razorpay_order_id, razorpay_signature}`: calls `provider.verify_payment_signature(...)`.
   - **Valid** → `SponsoredPost.status = "paid"`, `paid_at` set, `razorpay_payment_id` stored, then `store_feed_service.emit_update(store.id, "sponsored", sponsored_post.message, ref_id=sponsored_post.id)` — this is the moment the post actually becomes visible (§3.2), fans out SSE to the store's own followers, and returns a `FeedItemResponse` (same shape `POST /stores/updates` returns today). `SponsoredPost.feed_post_id` is set to the new `StoreFeedPost.id`.
   - **Invalid** → `SponsoredPost.status = "failed"`, `400`. No `StoreFeedPost` row is created — a failed/unconfirmed payment never reaches any shopper's feed. The store can retry by creating a new `SponsoredPost` (a fresh `POST /stores/sponsored-posts` call, fresh Razorpay Order) — a failed pending post is not resumable, mirroring `Subscription.checkout()`'s "already checked out" idempotency being the only reuse case in the existing subscription flow.

This confirm-then-post ordering (rather than posting immediately and reconciling via webhook after) is why it's a synchronous `confirm` endpoint rather than the subscription flow's webhook-driven state machine: a sponsored post is a single moment-in-time purchase, not an ongoing subscription with multiple future events to reconcile, so there's no need for the two-mechanism (webhook + lazy recompute) machinery `SPEC_SUBSCRIPTION.md` §3.2 uses. No webhook endpoint is added for sponsored posts in v1.

### 3.4 Admin price control

Reuses `_require_admin` (`X-Admin-Token`), same pattern as `SPEC_SUBSCRIPTION.md` §3.5:
- `GET /sponsored-posts/admin/price` — current price (most recent `SponsoredPostPricing` row)
- `POST /sponsored-posts/admin/price` — body `{"price_paise": int}`; inserts a new `SponsoredPostPricing` row. Not retroactive — a `SponsoredPost` already created (paid or pending) keeps its own snapshotted `amount_paise`; only a fresh `POST /stores/sponsored-posts` call after this picks up the new price.

## 4. Data Contracts

```json
// POST /stores/sponsored-posts  →  request / response (store, billing-gated)
{ "message": "Grand opening! 20% off everything this weekend." }
→ {
  "sponsored_post_id": "e1f2...",
  "razorpay_order_id": "order_abc123",
  "amount_paise": 19900,
  "razorpay_key_id": "rzp_live_..."
}

// POST /stores/sponsored-posts/{id}/confirm  →  request / response (store, owner only)
{ "razorpay_payment_id": "pay_xyz789", "razorpay_order_id": "order_abc123", "razorpay_signature": "..." }
→ {   // FeedItemResponse — same shape as POST /stores/updates
  "id": "b3f1...", "store_id": "a1c2...", "store_name": "Fresh Mart",
  "update_type": "sponsored", "message": "Grand opening! 20% off everything this weekend.",
  "ref_id": "e1f2...", "created_at": "2026-08-22T10:00:00Z"
}
// 400 if the signature doesn't verify — SponsoredPost.status becomes "failed", no feed post created

// GET /stores/sponsored-posts  →  response (store, own spend history)
{ "items": [
    { "id": "e1f2...", "message": "...", "amount_paise": 19900, "status": "paid",
      "created_at": "...", "paid_at": "..." }
  ] }

// GET /sponsored-posts/admin/price  →  response (X-Admin-Token)
{ "price_paise": 19900, "effective_since": "2026-08-22T00:00:00Z" }

// POST /sponsored-posts/admin/price  →  request / response (X-Admin-Token)
{ "price_paise": 29900 }
→ { "price_paise": 29900, "effective_since": "2026-09-01T00:00:00Z" }
```

`GET /feed` and `GET /stores/{store_id}/updates` response shapes are unchanged (`SPEC_STORE_FOLLOW_FEED.md` §4) — a sponsored item is just a `FeedItemResponse` with `update_type: "sponsored"`. The frontend renders a "Sponsored" badge off that field alone; no new response field needed.

## 5. Required Changes

**Backend (`groceror`)**
- `engine/billing/provider.py` — add `RazorpayOrder` dataclass, `create_order`/`verify_payment_signature` to the `BillingProvider` Protocol
- `engine/billing/razorpay_provider.py` — implement both against the real Razorpay SDK (`client.order.create`, `client.utility.verify_payment_signature`)
- `engine/billing/fake_provider.py` — implement both deterministically for tests (mirrors existing fake subscription methods); needs a `VALID_SIGNATURE`-style sentinel like the existing webhook fake
- `models/entity/sponsored_post_pricing_entity.py` — new `SponsoredPostPricing` (§3.1)
- `models/entity/sponsored_post_entity.py` — new `SponsoredPost` (§3.1)
- `models/db.py` — register both new entities
- New alembic migration (down_revision `c7d8e9f0a1b2`, the current head) adding `sponsoredpostpricing` and `sponsoredpost` tables, seeding one initial `SponsoredPostPricing` row at ₹199 so `get_current_price()` never has to handle "no price configured"
- `models/service/store_feed_service.py` — add `"sponsored"` to `UPDATE_TYPES`; change `list_feed`/`count_feed`/`unread_count`'s filter to the OR-scope in §3.2
- New `models/service/sponsored_post_service.py` — `get_current_price()`/`set_price()` (mirrors `subscription_service.get_current_plan`/`set_plan_price`), `create_pending(store, message)` (calls `provider.create_order`), `confirm(sponsored_post, payment_id, order_id, signature)` (verifies + calls `store_feed_service.emit_update`), `list_for_store(store_id)`
- New `api/sponsored_post_api.py` — `POST /stores/sponsored-posts`, `POST /stores/sponsored-posts/{id}/confirm`, `GET /stores/sponsored-posts`, `GET /sponsored-posts/admin/price`, `POST /sponsored-posts/admin/price`
- `main.py` — register `sponsored_post_apis`
- Tests: unit tests for `sponsored_post_service` (price snapshot-not-retroactive, pending→paid/failed transitions); integration tests for the router (billing-lock gate on create, ownership on confirm, invalid-signature → 400 and no feed post, valid-signature → feed post appears in `GET /feed` for a **non-follower**, admin price read/write)

**Frontend (`groceror-fe`)**
- `client/src/pages/following.tsx` — feed item renderer checks `update_type === "sponsored"` and shows a "Sponsored" badge/label distinct from organic updates
- `client/src/pages/dashboard.tsx` (store owner) — a "Sponsored Posts" composer: message input, shows current price (`GET /sponsored-posts/admin/price` is admin-only, so this needs a shopper-facing price-preview endpoint or the price returned in the `POST /stores/sponsored-posts` response is shown post-hoc — simplest: show the price only after `POST /stores/sponsored-posts` returns `amount_paise`, right before opening Checkout), opens Razorpay Checkout (Orders mode) with the returned `order_id`, calls `/confirm` on success; a spend-history list from `GET /stores/sponsored-posts`
- `client/index.html` — Razorpay Checkout script tag, if not already added by `SPEC_SUBSCRIPTION.md`'s implementation
- `client/src/types/models.ts` — add `SponsoredPost` type

## 6. Error Handling

- `POST /stores/sponsored-posts` requires a store profile and is billing-gated (402 if locked) — same as every other store mutation endpoint
- `POST /stores/sponsored-posts/{id}/confirm`: 404 if the `SponsoredPost` doesn't exist or isn't owned by the caller's store; 400 if the Razorpay signature doesn't verify (status → `failed`, no feed post created); 409 if the post is already `paid` (idempotency guard against a duplicate confirm call)
- A `SponsoredPost` stuck in `pending` forever (store opened Checkout, never completed or abandoned it) is inert — it never becomes a feed post and is invisible to every query except the store's own `GET /stores/sponsored-posts` spend history. No cleanup job for v1 (see Out of Scope)
- `GET /sponsored-posts/admin/price`, `POST /sponsored-posts/admin/price` require `X-Admin-Token`, same 403 behavior as the subscription admin endpoints
- `limit`/`offset` on any paginated endpoint reuses the existing `_clamp_limit` pattern already in `store_feed_api.py`

## 7. Implementation Order

1. Confirm the real Razorpay Orders API shape (`order.create`, `utility.verify_payment_signature`) against a test account — same unverified-assumption flag as §3.3; resolve before writing the provider methods against the assumption
2. Backend: `BillingProvider.create_order`/`verify_payment_signature` on the Protocol + `RazorpayProvider` + `FakeBillingProvider`
3. Backend: `SponsoredPostPricing` + `SponsoredPost` entities, migration, `models/db.py` registration
4. Backend: `sponsored_post_service.py` (price get/set, `create_pending`, `confirm`) + unit tests
5. Backend: broaden `store_feed_service.list_feed`/`count_feed`/`unread_count` to the OR-scope (§3.2) + a regression test confirming a **non-follower** now sees a sponsored post while still not seeing that store's non-sponsored updates
6. Backend: `sponsored_post_api.py` router (all five endpoints) + `main.py` registration + integration tests (billing gate, ownership, signature failure path, end-to-end paid post visible in a non-follower's `GET /feed`)
7. Frontend: dashboard composer + Checkout (Orders mode) + confirm call + spend-history list
8. Frontend: "Sponsored" badge on `following.tsx` feed items
9. End-to-end check: a store with zero followers buys a sponsored post, a shopper who has never followed that store sees it in `GET /feed` tagged `sponsored`, the store's own `GET /stores/{id}/updates` also shows it, and a `locked` store's attempt to buy one 402s

## 8. Out of Scope (this version)

- Refunds or cancellation of a paid sponsored post — matches the no-expiry, immutable-log decision; `DELETE /stores/updates/{update_id}` already refuses non-`announcement` types
- Prepaid credits/wallet — pay-per-post only, per the payment-model decision
- Pinned/boosted feed placement, frequency capping, or any ranking beyond `created_at` — pure interleaving, per the placement decision
- Geographic or segment targeting ("post to shoppers in this city only") — a sponsored post reaches literally every shopper, no scoping
- Real-time SSE push of a sponsored post to non-followers — the existing `store_update` SSE channel stays follower-only (§3.2); a non-follower sees it on next `GET /feed` poll, not instantly
- A cleanup/expiry job for `SponsoredPost` rows stuck in `pending` (abandoned checkout) — they're simply invisible and inert, no retention policy
- Rate limiting how many sponsored posts a store can buy per day/week
- Moderation/review of sponsored post content before it goes live — same trust level as the existing free-text `announcement` type, no new content-review step
- A public, non-authenticated price-preview endpoint — the price a store sees is whatever `POST /stores/sponsored-posts` returns at checkout time, not fetchable in advance without initiating a checkout
- GST/tax-compliant invoicing for sponsored-post payments — same deferred gap `SPEC_SUBSCRIPTION.md` §8 already flags for subscription billing
