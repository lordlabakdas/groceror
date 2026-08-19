# Delivery Dispatch (Shiprocket Quick)

**Status:** Draft — under discussion, nothing implemented yet
**Author:** Siddharth Gangadhar + Claude
**Date:** 2026-08-17
**Services affected:** groceror (backend), groceror-fe (frontend)

Vendor evaluation (Shadowfax → Porter/Dunzo/Delhivery ruled out → Shiprocket Quick) and the v1 product decisions below were made in a separate planning session and are recorded, with full rationale, in `GROCEROR_CONTEXT.md` §10 and its 2026-08-17 addenda in that file's changelog. This spec assumes those decisions and focuses on implementation.

## 1. Background & Goal

Groceror has no delivery execution today. The shipped `/delivery-zones` feature (`delivery_zone_entity.py`, `api/delivery_zone_api.py`) only lets a store define a geofence (lat/lng/radius) — no courier, rider, or dispatch software sits behind it. Fulfillment within that zone happens outside Groceror entirely (store self-delivery or shopper pickup).

**Goal:** integrate Shiprocket Quick (Shiprocket's hyperlocal delivery product) so a store owner can request a courier for a ready order, and the shopper sees a real delivery fee and status instead of nothing. This is v1 — see **Out of Scope** for what's deliberately deferred.

Decided shape (from `GROCEROR_CONTEXT.md` §10):
- Delivery fee is a Shiprocket Quick–quoted line item, **pass-through** to the shopper (no Groceror markup, for now)
- Dispatch is **manually triggered by the store owner** ("Request Delivery"), not automatic
- If a delivery address is outside Shiprocket Quick's coverage, it **just fails** — no reconciliation with the store's self-defined delivery zone
- Vendor access is behind a thin internal interface so a future vendor swap doesn't touch order/checkout code

## 2. Current State

| Piece | Status |
|---|---|
| Delivery zone geofence | Exists — `delivery_zone_entity.py`, `/delivery-zones` (`api/delivery_zone_api.py`) |
| Order status lifecycle | Exists — `pending → confirmed → ready → delivered → cancelled` (`VALID_STATUSES`, `api/validators/order_validation.py`); no delivery-specific state |
| Order status updates + SSE | Exists — `update_order_status()` (`models/service/orders_service.py:281`), pushes `order_status_update` to the shopper via `sse_publish` (`api/order_api.py:212`) |
| Delivery execution | **Gap G1** — no courier/rider assignment anywhere in either repo |
| Delivery fee | **Gap G2** — no fee calculation; `cart-drawer.tsx` posts straight to `POST /order/create-order` with no delivery cost in the flow |
| Vendor integration | **Gap G3** — no third-party logistics API client exists; no `ShiprocketConfig`-style entry in `config.py` |
| Shopper delivery address | **Gap G4** — `User.location` (`models/entity/user_entity.py`) is a single optional free-text string, no lat/lng, and `CreateOrderRequest` doesn't collect an address at all today. A quote or dispatch call needs a structured dropoff point; nothing currently captures one per order. |
| Real-time delivery status | **Gap G5** — SSE (`api/sse_bus.py`) exists for order status but nothing delivery-specific |

## 3. Proposed Design

### 3.1 Vendor abstraction

A small internal interface, implemented once against Shiprocket Quick, so the vendor can be swapped later without touching checkout or order code:

```python
class DeliveryProvider(Protocol):
    def get_quote(self, pickup: Coordinates, dropoff: Coordinates, weight_kg: float) -> Quote: ...
    def create_delivery(self, quote_id: str, order_ref: str) -> VendorDelivery: ...
    def get_status(self, vendor_delivery_id: str) -> DeliveryStatus: ...
    def cancel(self, vendor_delivery_id: str) -> None: ...
```

`ShiprocketQuickProvider` implements this against their REST API. **Open item, not yet verified:** exact auth scheme, quote-expiry window, and webhook signature format — Shiprocket Quick's technical docs weren't independently confirmed during vendor evaluation (see `GROCEROR_CONTEXT.md` §10 addendum 2). First implementation task is pulling real docs from a Shiprocket business account and adjusting this interface's shape if needed before the rest is built.

`config.py` gets a `ShiprocketConfig` class matching the existing `TwilioConfig`/`EmailConfig` pattern:

```python
class ShiprocketConfig(object):
    """Shiprocket Quick hyperlocal delivery configuration"""
    API_KEY: ClassVar[str] = _env("SHIPROCKET_API_KEY")
    API_SECRET: ClassVar[str] = _env("SHIPROCKET_API_SECRET")
```
(Exact env var names TBD once real credentials are issued.)

### 3.2 New entity: `Delivery`

A separate entity, not an overload of `Order.status` — matches how the codebase already hangs concerns off `Order` (`LoyaltyTransaction`, `Coupon`) rather than cramming them into one status field:

```python
class Delivery(SQLModel, table=True):
    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    order_id: UUID = Field(foreign_key="order.id", unique=True, index=True)
    store_id: UUID = Field(foreign_key="store.id", index=True)
    vendor: str = Field(default="shiprocket_quick")  # data, not an enum — future-swap-friendly
    vendor_quote_id: Optional[str] = None
    vendor_delivery_id: Optional[str] = None
    status: str = Field(default="quoted", index=True)  # quoted/requested/confirmed/picked_up/in_transit/delivered/failed/cancelled
    quoted_fee: float
    rider_name: Optional[str] = None
    rider_phone: Optional[str] = None
    tracking_url: Optional[str] = None
    requested_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    raw_webhook_payload: Optional[str] = None  # last webhook body, for debugging
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
```

Must be added to `models/db.py`'s explicit entity-import block (constitution Principle II) or the table silently won't exist under test.

### 3.3 Checkout: the quote step

Grocery orders need packing time, so the quote happens at checkout (pricing the shopper sees) but dispatch happens later (§3.4, store-triggered). Two different moments, two different failure postures:

- **New endpoint:** `POST /order/delivery-quote` — takes a dropoff address (lat/lng, collected from the shopper at checkout, addressing Gap G4) and the store's pickup point (reused from `DeliveryZone.latitude`/`longitude` — already exists per store). Returns `{quote_id, fee, expires_at}`.
- This call is **blocking and essential**, unlike the `Mailer().send()` pattern (Principle V's "fail soft, log, continue" applies to *non-essential* side effects — a wrong or missing delivery fee is not that). If the quote call fails or Shiprocket Quick reports the address unserviceable, checkout falls back to a "delivery unavailable — pickup only" state; it does not block placing the order for pickup.
- `CreateOrderRequest` gets an optional `quote_id` field. `create_order()` re-validates the quote hasn't expired before finalizing an order that includes delivery; an expired quote returns `409 Conflict` and the frontend re-quotes rather than silently charging a stale price.
- `Order` gets a new nullable `delivery_fee` field, included in `total_price` at creation — kept on `Order` rather than only on `Delivery` so every existing place that reads `total_price` (order history, dashboard, store orders) doesn't need to learn to sum two tables.
- `Order` also gets `delivery_address_line`, `delivery_lat`, `delivery_lng` (nullable) — addressing Gap G4. Captured once at checkout, not read from `User.location`, since a shopper may want delivery somewhere other than their profile address.

### 3.4 Dispatch: the store-triggered step

- `store-orders.tsx` shows a **"Request Delivery"** button once `order.status == "ready"` (existing status — no new `Order` status needed to gate this).
- **New endpoint:** `POST /order/{order_id}/request-delivery` (store-authenticated, same `_get_store_profile` dependency as `update_order_status`). Creates/updates the `Delivery` row (`status=requested`) and calls `ShiprocketQuickProvider.create_delivery()` using the quote already locked at checkout.
- If dispatch creation fails here (quote long expired, vendor rejects, pickup point moved), `Delivery.status = failed`, the store owner sees a clear message, and **there is no automatic retry** — the store falls back to self-arranged delivery, matching the "keep it simple, fail" decision. This failure mode *is* the Mailer-style case: dispatch is a side effect on an order that already exists and is already paid for, so failing soft (log, surface, move on) is the right posture here, unlike the checkout-time quote.

### 3.5 Webhook ingestion & real-time status

- **New endpoint:** `POST /webhooks/shiprocket-quick` — ingests status updates (`picked_up` / `in_transit` / `delivered` / `failed`), verifies the request against Shiprocket Quick (signature mechanism TBD, see §3.1), and updates the matching `Delivery` row by `vendor_delivery_id`. Unverified requests get `401` and no state change, to prevent spoofed status updates.
- On each update, push `delivery_status_update` over SSE to the shopper (`sse_publish(str(order.user_id), ...)`), mirroring the existing `order_status_update` pattern in `update_order_status`.
- When a webhook reports `delivered`, also set `Order.status = "delivered"` — reusing the existing valid status rather than inventing a parallel one.

### 3.6 Coverage handling

No upfront reconciliation between a store's self-defined `/delivery-zones` geofence and Shiprocket Quick's real coverage (decided, kept simple for v1). The `delivery-quote` call **is** the serviceability check — if Shiprocket Quick reports the dropoff unserviceable, that surfaces to the shopper as "delivery unavailable for this address" before an order is even placed, which is friendlier than failing after a store has already packed the order.

## 4. Data Contracts

```json
// POST /order/delivery-quote  →  request
{ "store_id": "uuid", "dropoff_lat": 13.0827, "dropoff_lng": 80.2707 }

// → response
{ "quote_id": "sq_abc123", "fee": 45.00, "expires_at": "2026-08-17T14:35:00Z" }

// POST /order/create-order  →  request gets one new optional field
{ "items": [...], "coupon_code": null, "points_to_redeem": 0,
  "quote_id": "sq_abc123",
  "delivery_address_line": "12 Anna Salai, T. Nagar",
  "delivery_lat": 13.0827, "delivery_lng": 80.2707 }

// POST /order/{order_id}/request-delivery  →  response
{ "delivery_id": "uuid", "status": "requested" }

// POST /webhooks/shiprocket-quick  →  inbound payload (illustrative; confirm real shape against vendor docs)
{ "vendor_delivery_id": "sq_del_789", "status": "picked_up",
  "rider_name": "...", "rider_phone": "...", "tracking_url": "..." }
```

## 5. Required Changes

**Backend (`groceror`)**
- `models/entity/delivery_entity.py`: new `Delivery` entity (§3.2)
- `models/db.py`: register `Delivery` in the entity-import block (Principle II)
- Alembic migration for `Delivery`, plus `Order.delivery_fee`, `Order.delivery_address_line`, `Order.delivery_lat`, `Order.delivery_lng`
- `config.py`: add `ShiprocketConfig`
- `engine/delivery/` (new): `DeliveryProvider` protocol + `ShiprocketQuickProvider` implementation + a fake/stub provider for tests (constitution Principle II — no live vendor calls in the test suite)
- `api/order_api.py`: new `POST /order/delivery-quote` and `POST /order/{order_id}/request-delivery` routes; extend `create_order()` to accept and validate `quote_id`
- `api/validators/order_validation.py`: `CreateOrderRequest` gets `quote_id`, `delivery_address_line`, `delivery_lat`, `delivery_lng`; new request/response models for the quote and dispatch endpoints
- New `api/webhook_api.py` (or extend an existing router): `POST /webhooks/shiprocket-quick`, with signature verification
- `models/service/orders_service.py`: quote-expiry validation in `create_order()`; new dispatch/webhook-handling logic (own service or extend `orders_service.py`)
- Tests: fake-provider unit tests for the quote/dispatch/webhook flows; integration test for expired-quote rejection; integration test for the unserviceable-address path

**Frontend (`groceror-fe`)**
- `client/src/components/cart-drawer.tsx`: fetch a delivery quote before "Place Order," show the fee as a line item, handle quote expiry (re-quote) and the pickup-only fallback when quoting fails
- New address-capture UI at checkout (Gap G4 — nothing collects a delivery address today)
- `client/src/pages/store-orders.tsx`: "Request Delivery" action once an order is `ready`; show `Delivery.status` and rider info once requested
- `client/src/pages/orders.tsx`: show delivery status/tracking to the shopper, updated live via the existing SSE hook (`use-sse.ts`) extended for `delivery_status_update`
- `client/src/types/models.ts`: add `Delivery`-related types

## 6. Error Handling

- Quote call fails or times out at checkout → delivery marked unavailable, shopper can still place a pickup-only order (fail soft, per §3.3)
- Quote expired by the time `create_order()` runs → `409 Conflict`, frontend re-quotes
- `request-delivery` call fails (vendor rejects, quote stale) → `Delivery.status = failed`, store notified, no auto-retry, store falls back to self-arranged delivery (fail soft, per §3.4)
- Webhook reports a failed delivery → `Delivery.status = failed`, SSE to shopper, `Order.status` is **not** auto-advanced to `delivered`
- Unverified/unsigned webhook request → `401`, logged, no state change

## 7. Implementation Order

1. Get a real Shiprocket Quick business account and confirm the actual API shape — resolve the "open item" in §3.1 before writing the provider against assumptions
2. Backend: `Delivery` entity + migration + `models/db.py` registration
3. Backend: `DeliveryProvider` interface + fake provider for tests + `ShiprocketQuickProvider`
4. Backend: `POST /order/delivery-quote`
5. Backend: extend `create_order()` for `quote_id` + delivery address fields, add `Order.delivery_fee`
6. Backend: `POST /order/{order_id}/request-delivery`
7. Backend: `POST /webhooks/shiprocket-quick` + SSE push
8. Frontend: checkout quote step + address capture in `cart-drawer.tsx`
9. Frontend: "Request Delivery" + status display in `store-orders.tsx`
10. Frontend: delivery status/tracking in `orders.tsx`
11. End-to-end check: place an order with a quote, request delivery, simulate webhook updates via the fake provider, confirm SSE and status propagate correctly on both the store and shopper sides

## 8. Out of Scope (this version)

- Delivery fee markup — pass-through only for v1 (`GROCEROR_CONTEXT.md` §10); revisit once there's real usage data
- Automatic dispatch on order-ready — manual "Request Delivery" only
- Live map tracking UI — `tracking_url` (if the vendor provides one) is surfaced as a plain link, no embedded map
- Multi-vendor fallback/routing — Shiprocket Quick only; the `DeliveryProvider` abstraction exists so this can be added later without reworking checkout/order code
- Zone-to-vendor-coverage reconciliation — the quote call is the serviceability check (§3.6), no upfront comparison against `/delivery-zones`
- Confirming whether Shiprocket Quick runs its own fleet or a decentralized partner network — doesn't block this design, but affects expected delivery-quality variance; still open per `GROCEROR_CONTEXT.md` §10
- Store Manager/Employee sub-roles being able to trigger dispatch — only the single `store`-role identity can, matching every other store-owner action today
