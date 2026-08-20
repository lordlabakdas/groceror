# Subscription Billing (Store-Owner SaaS Fee)

**Status:** Draft — under discussion, nothing implemented yet
**Author:** Siddharth Gangadhar + Claude
**Date:** 2026-08-19
**Services affected:** groceror (backend), groceror-fe (frontend)

Payment provider, pricing model, and lapse-enforcement posture were decided in a scoping conversation preceding this document and are recorded here rather than in `GROCEROR_CONTEXT.md` (no addendum was added there — see the Maintenance Rule, §26, if this spec is later revisited and that file should be reconciled). This spec assumes those decisions and focuses on design.

## 1. Background & Goal

Groceror has no revenue model today (`GROCEROR_CONTEXT.md` §10, §20, §21 — "no billing system to even test this against"). Every store owner uses the platform for free, indefinitely. The `Store` entity already has an `is_active` flag store owners toggle themselves (`POST /store/{id}/activate|deactivate`) and an admin-gated `is_verified` flag (`POST /store/{id}/verify`, header `X-Admin-Token`), but nothing ties store operation to payment.

**Goal:** the Groceror platform owner charges each store owner a flat recurring fee to keep their storefront live and operating. This is v1 — see **Out of Scope** for what's deliberately deferred.

Decided shape:
- **Payment provider: Razorpay**, specifically Razorpay Subscriptions (recurring auto-debit via UPI/card mandate) — not Stripe, despite a same-named `feat/stripe-payments` worktree/branch existing in this repo from earlier exploration; that branch is unrelated to this spec and should not be reused for it.
- **Pricing: a single flat plan** — no tiers, no usage-based/GMV-percentage billing. One price, billed monthly, per store.
- **Enforcement: grace period, then hard lock.** A failed or missing payment doesn't lock a store out immediately — it gets a warning window to resolve, then the store goes offline to buyers and read/write-restricted for the owner until payment resolves.
- **Billing unit is the `Store`, not the owner entity.** `Store.entity_id` has no uniqueness constraint (`get_stores_by_entity` returns a list), so one owner could in principle run multiple stores — each is billed independently, matching the existing per-store `is_active` visibility model. In practice today's UI only ever creates one store per entity, so this rarely matters yet.

- **Plan price is admin-configurable, not a hardcoded constant.** The Groceror platform owner can change what new subscriptions are charged, via an authenticated admin endpoint — see §3.1 and §3.5.

**Proposed default constants (confirm before implementation, easy to change — they're constants, not schema):**

| Constant | Proposed value |
|---|---|
| Plan price | ₹999/month (initial value — thereafter admin-editable, §3.5) |
| Trial length | 14 days from store creation, no card required to start |
| Grace period | 7 days from first missed/failed payment |

## 2. Current State

| Piece | Status |
|---|---|
| Any payment/billing integration | **Gap G1** — no Razorpay, Stripe, or other payment provider client anywhere in the codebase |
| Store lifecycle beyond active/inactive | **Gap G2** — `Store.is_active` is a single boolean, entirely owner-controlled (`store_service.py:94-97`); no billing-driven state |
| Buyer-facing store visibility | Exists — `get_all_active_stores()` (`store_service.py:101`) filters `is_active == True`; used by `GET /store/` (`store_api.py:85`) |
| Store-owner write-endpoint gating | Exists, but auth-only — every store-scoped router (`coupon_api.py`, `bulk_rule_api.py`, `delivery_zone_api.py`, `flash_sale_api.py`, `stock_alert_api.py`, `featured_store_api.py`, `order_api.py`, `inventory_api.py`) defines its own local `_get_store()`/`_get_store_profile()` dependency that resolves `auth_required`'s `PhoneVerification` to a `Store` row — no shared helper, and none of them check anything beyond "does this store belong to this caller" |
| Admin concept | Partial — `_require_admin` (`store_api.py:249`) is a single shared-secret header (`X-Admin-Token`, `AdminConfig.ADMIN_TOKEN`), not a JWT role; used only for store verify/unverify today |
| Email side-effect pattern | Exists — `Mailer().send(...)` wrapped in try/except at the order-confirmation call site (Principle V); no billing-related email exists yet |
| Frontend billing UI | **Gap G3** — nothing; no `/billing` route, no `Subscription` type in `models.ts` |
| Frontend 402/lock handling | **Gap G4** — `queryClient.ts` has no concept of a payment-required response; nothing intercepts it |

## 3. Proposed Design

### 3.1 New entities

```python
class SubscriptionPlan(SQLModel, table=True):
    """Append-only price history. The current price is the most recent row
    (order by created_at desc, limit 1) — never mutated in place, so changing
    the price doesn't touch any existing Subscription and leaves a free audit
    trail of what Groceror charged and when."""
    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    price_paise: int                                       # e.g. 99900 = ₹999.00/month
    razorpay_plan_id: Optional[str] = None                 # set once created in Razorpay (§3.4)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: str = Field(default="admin")               # informational only — X-Admin-Token has no identity

class Subscription(SQLModel, table=True):
    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    store_id: UUID = Field(foreign_key="store.id", unique=True, index=True)
    status: str = Field(default="trialing", index=True)
    # trialing / active / grace / locked / cancelled
    razorpay_customer_id: Optional[str] = None
    razorpay_subscription_id: Optional[str] = None
    plan_price_paise: Optional[int] = None                 # snapshotted at checkout (§3.4) — null during trial
    trial_end: datetime
    current_period_start: Optional[datetime] = None
    current_period_end: Optional[datetime] = None
    grace_period_end: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class SubscriptionInvoice(SQLModel, table=True):
    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    subscription_id: UUID = Field(foreign_key="subscription.id", index=True)
    razorpay_payment_id: Optional[str] = None
    amount_paise: int
    status: str                                             # paid / failed
    period_start: datetime
    period_end: datetime
    paid_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
```

All three must be added to `models/db.py`'s explicit entity-import block (constitution Principle II) or their tables silently won't exist under test.

**Why price lives in the DB, not `config.py`:** an env-var constant can't be changed by an admin at runtime without a redeploy — the whole point of this requirement is that the platform owner changes it through the product, not through code. `SubscriptionPlan` is the source of truth; `RazorpayConfig` (§5) only holds credentials, not the price.

**Why `Subscription.plan_price_paise` is a snapshot, not a live lookup:** once a store owner has actually checked out and is being charged a real Razorpay subscription amount, a later admin price change must not silently re-price them mid-contract — see §3.5's grandfathering rule. Before checkout (`status="trialing"`, `plan_price_paise IS NULL`), the price shown to the owner (`GET /subscription/status`, the billing page) is the *current* `SubscriptionPlan` price, looked up live — it's still just a preview, nothing has been charged yet.

`Store` gets one new field: `is_billing_locked: bool = Field(default=False)`. Deliberately **separate** from `is_active` rather than reusing it — `is_active` is the owner's own self-service pause switch (`activate`/`deactivate_store`); overloading it for billing would mean an owner's deliberate pause gets silently undone on payment, or a billing lock gets silently undone by an unrelated owner action. `get_all_active_stores()` and any other buyer-facing store query change to `is_active == True AND is_billing_locked == False`.

### 3.2 State machine

```
trialing --(first successful charge)--> active
trialing --(trial_end passes, never authorized)--> grace
active   --(payment fails / Razorpay reports pending)--> grace
grace    --(payment succeeds)--> active
grace    --(grace_period_end passes unresolved)--> locked
locked   --(payment succeeds)--> active
any      --(owner or admin cancels)--> cancelled
```

`Subscription` rows are created automatically inside `StoreService.create_store()`, in the same transaction as the `Store` row — a store cannot exist without a subscription record, avoiding a separate frontend orchestration step or a race where a store briefly exists unbilled. `status="trialing"`, `trial_end = now + 14 days`, no Razorpay objects created yet (no card required to start the trial, per the proposed default).

Transitions are driven by two things:
1. **Razorpay webhooks** (`subscription.activated`, `subscription.charged` → active; `subscription.pending`, `subscription.halted` → grace; `subscription.cancelled` → cancelled) — real-time, but only fire once a subscription has actually been created (i.e., after the owner completes checkout).
2. **A lazy check on read**, not a background job/cron (monolith-simplicity, Principle VI — no new scheduler infrastructure for v1): `subscription_service.get_status(store_id)` computes whether `trialing` has passed `trial_end` with no Razorpay subscription (→ `grace`), or whether `grace` has passed `grace_period_end` (→ `locked`), updating the row if so, every time it's read. Since it's read on essentially every store-owner request (§3.3), staleness is bounded by "time until this store owner's next request" — acceptable for a grace/lock transition that's measured in days, not something with a real-time SLA.

On the `active`/`grace` → `grace` transition (payment fails, or trial lapses unauthorized), send one email via the existing `Mailer()` pattern (Principle V — wrapped in try/except, a Resend outage must not block the state transition), telling the owner they have `grace_period_end - now` to resolve it. One email, not a reminder sequence (see Out of Scope).

### 3.3 Enforcement

Read endpoints (viewing the dashboard, own orders, own inventory) stay open in every state, including `locked` — a locked-out owner must still be able to see what's happening and reach the billing page to pay, and blocking in-flight order visibility would hurt the shopper who already paid, not just the delinquent owner.

**Mutation** endpoints that create or change storefront-facing content are gated: inventory add/edit, coupon create, flash sale create, bulk rule create, delivery zone create/edit, store profile update. Order status updates and delivery dispatch (`order_api.py`) are explicitly **not** gated — a locked store can still fulfill orders already placed; new orders can't arrive anyway once `is_billing_locked` hides the store from buyers (§3.1).

Rather than introduce a new shared dependency (the codebase's existing convention, seen across `coupon_api.py`, `bulk_rule_api.py`, `delivery_zone_api.py`, `flash_sale_api.py`, `stock_alert_api.py`, `featured_store_api.py`, is a small locally-duplicated `_get_store()` per file, not a shared one), each relevant file's existing `_get_store()` gets one added line calling a new `subscription_service.assert_billing_ok(store)` helper, which raises `HTTPException(402, ...)` if the computed status (§3.2) is `locked`. This matches the codebase's existing duplication-over-abstraction style rather than fighting it.

### 3.4 Checkout flow (Razorpay)

**Everything in this subsection is the assumed shape of Razorpay's Subscriptions API from general knowledge, not verified against current Razorpay docs or a real account — same posture as `SPEC_DELIVERY_DISPATCH.md` took with Shiprocket Quick. First real implementation step is a Razorpay test account and confirming this shape, not writing code against the assumption.**

1. A Razorpay `Plan` is created for the *current* `SubscriptionPlan` price the first time it's needed (lazily, on first checkout after that price becomes current) rather than at admin-edit time — creating a Razorpay `Plan` costs nothing to defer and this avoids ever calling Razorpay from the admin price-change request itself (§3.5 stays a pure DB write, so it can't fail because Razorpay is down). `SubscriptionPlan.razorpay_plan_id` is cached once created and reused for every subsequent checkout at that price.
2. `POST /subscription/checkout` (store owner, authenticated): resolves the current `SubscriptionPlan` (creating its Razorpay `Plan` if not yet cached, per above), creates a Razorpay `Customer` (if `razorpay_customer_id` is unset) and a Razorpay `Subscription` against that plan, `start_at` = the store's `trial_end` (so the first charge doesn't happen until the trial is over even if the owner authorizes early). Snapshots `Subscription.plan_price_paise` to the resolved price at this moment. Returns the Razorpay `subscription_id` + publishable key for the frontend Checkout widget.
3. Frontend opens Razorpay's Checkout JS with that `subscription_id`; the owner authorizes an auto-debit mandate (typically a ₹0 or nominal verification transaction — exact behavior unverified, see above).
4. Razorpay webhooks (`POST /subscription/webhook`) drive the state machine from there (§3.2). Signature verification uses Razorpay's SDK utility against a webhook secret in config; an unverified request gets `401` and no state change, mirroring the delivery-dispatch webhook's posture.

### 3.5 Admin visibility and price control

Reuses the existing `_require_admin` (`X-Admin-Token` header) pattern rather than introducing a new admin auth scheme:
- `GET /subscription/admin/list` — every store's subscription status, for the platform owner to see trial/active/grace/locked counts and MRR (`sum(plan_price_paise) where status == "active"` — note this reflects each store's *snapshotted* price, so MRR is a mix of old and new prices during any period where grandfathered stores coexist with new ones, which is correct, not a bug)
- `POST /subscription/{store_id}/admin/unlock` — manual override (goodwill/support case): sets `status="active"`, `is_billing_locked=False`, extends `current_period_end` by one cycle, without a real Razorpay charge
- `GET /subscription/admin/plan-price` — current price (most recent `SubscriptionPlan` row)
- `POST /subscription/admin/plan-price` — body `{"price_paise": int}`; inserts a new `SubscriptionPlan` row. **Not retroactive**: existing subscriptions keep the price snapshotted onto them at their own checkout time (§3.1) — nothing about an active, grace, or locked subscription changes when this runs. The new price only takes effect for stores that check out (§3.4) after this call. This is a deliberate grandfathering choice, not a limitation of the schema — flagged here as a decision worth confirming, same as the pricing/trial/grace defaults in §1, since "does a price change apply to existing subscribers" is a real business call and grandfathering was chosen as the safer default (no surprise mid-contract repricing, no proration math, which is already Out of Scope).

## 4. Data Contracts

```json
// GET /subscription/status  →  response (store owner)
{
  "status": "grace",
  "plan_price_paise": 99900,
  "trial_end": "2026-09-02T00:00:00Z",
  "current_period_end": "2026-10-02T00:00:00Z",
  "grace_period_end": "2026-10-09T00:00:00Z",
  "razorpay_subscription_id": "sub_abc123",
  "checkout_needed": false
}

// POST /subscription/checkout  →  response
{ "razorpay_subscription_id": "sub_abc123", "razorpay_key_id": "rzp_live_..." }

// POST /subscription/cancel  →  response
{ "status": "cancelled", "effective_at": "2026-10-02T00:00:00Z" }

// POST /subscription/webhook  →  inbound payload (illustrative; confirm real shape against Razorpay docs)
{ "event": "subscription.charged",
  "payload": { "subscription": { "entity": { "id": "sub_abc123", "status": "active",
    "current_start": 1730000000, "current_end": 1732678400 } },
    "payment": { "entity": { "id": "pay_xyz789", "amount": 99900 } } } }

// GET /subscription/admin/list  →  response (X-Admin-Token)
{ "subscriptions": [
    { "store_id": "uuid", "store_name": "...", "status": "active", "plan_price_paise": 99900, "current_period_end": "..." }
  ],
  "mrr_paise": 499500 }

// GET /subscription/admin/plan-price  →  response (X-Admin-Token)
{ "price_paise": 99900, "effective_since": "2026-08-19T00:00:00Z" }

// POST /subscription/admin/plan-price  →  request / response (X-Admin-Token)
{ "price_paise": 149900 }
→ { "price_paise": 149900, "effective_since": "2026-09-01T00:00:00Z", "note": "applies to new checkouts only; existing subscriptions keep their snapshotted price" }
```

## 5. Required Changes

**Backend (`groceror`)**
- `models/entity/subscription_plan_entity.py`: new `SubscriptionPlan` entity (§3.1)
- `models/entity/subscription_entity.py`: new `Subscription` entity (§3.1)
- `models/entity/subscription_invoice_entity.py`: new `SubscriptionInvoice` entity (§3.1)
- `models/entity/store_entity.py`: add `is_billing_locked` field
- `models/db.py`: register all three new entities (Principle II)
- Alembic migration for all three new tables + `Store.is_billing_locked`; migration seeds one initial `SubscriptionPlan` row at the proposed ₹999/month default so `get_current_plan()` never has to handle "no plan exists yet"
- `config.py`: add `RazorpayConfig` (`KEY_ID`, `KEY_SECRET`, `WEBHOOK_SECRET`) — credentials only, **not** the price (that's `SubscriptionPlan`, §3.1), matching the existing `TwilioConfig`/`EmailConfig` pattern
- `requirements.txt`: add `razorpay`
- New `models/service/subscription_service.py`: state machine (§3.2), `assert_billing_ok()` (§3.3), Razorpay client calls incl. lazy Plan creation (§3.4), admin summary/MRR + plan-price read/write (§3.5)
- `models/service/store_service.py`: `create_store()` also creates the trial `Subscription` row in the same transaction
- New `api/subscription_api.py`: `GET /subscription/status`, `POST /subscription/checkout`, `POST /subscription/cancel`, `POST /subscription/webhook`, `GET /subscription/admin/list`, `POST /subscription/{store_id}/admin/unlock`, `GET /subscription/admin/plan-price`, `POST /subscription/admin/plan-price`
- `store_service.py`: `get_all_active_stores()` (and any other buyer-facing store query) filters `is_billing_locked == False`
- Add `subscription_service.assert_billing_ok(store)` call to the mutation-path `_get_store()`/equivalent in: `coupon_api.py`, `bulk_rule_api.py`, `delivery_zone_api.py`, `flash_sale_api.py`, `inventory_api.py`, `stock_alert_api.py`, `store_api.py` (profile update only, not activate/deactivate)
- `main.py`: register `subscription_apis` router
- Tests: unit tests for the state machine at each transition boundary (trial→grace, grace→locked, grace→active); integration test for a fake Razorpay webhook driving status changes; integration test confirming a locked store's mutation endpoints 402 while its order-fulfillment endpoints still work; unit test that an admin plan-price change does **not** alter any existing `Subscription.plan_price_paise`, only what a fresh checkout snapshots; a fake/stub Razorpay client for tests, matching the fake-provider pattern from delivery dispatch (constitution Principle II — no live vendor calls under test)

**Frontend (`groceror-fe`) — store-owner side**
- New `client/src/pages/billing.tsx`: status badge (trial/active/grace/locked with relevant dates), "Set up payment" / "Manage subscription" button opening Razorpay Checkout, invoice history table
- `client/src/App.tsx`: `<Route path="/billing">{() => <StoreOwnerRoute component={Billing} />}</Route>`
- `client/src/components/layout.tsx`: "Billing" nav link for store owners; a persistent banner when status is `grace` or `locked`, linking to `/billing`
- New `client/src/hooks/use-subscription-status.ts` (or similar): TanStack Query hook polling `GET /subscription/status`, feeding both the banner and route-level lock behavior
- `client/src/lib/queryClient.ts`: handle `402` responses distinctly from other errors (surface a toast/redirect to `/billing` rather than a generic failure)
- `client/index.html`: add Razorpay Checkout script tag (`checkout.razorpay.com/v1/checkout.js`)
- `client/src/types/models.ts`: add `Subscription`/`SubscriptionInvoice` types

**Frontend (`groceror-fe`) — admin side**

A minimal internal ops page, not a general admin/RBAC system (§8) — the MRR/status list and the unlock/plan-price actions are what actually justify a UI, per the reconsideration above; store verify/unverify staying curl-only is unaffected.
- New `client/src/pages/admin-billing.tsx`: on mount, if no admin token is stored, shows a single token-entry form (not a phone/OTP flow — this isn't the JWT auth system); once entered, stores it under a new `localStorage` key (`groceror_admin_token`, deliberately separate from `groceror_auth_token` so it can't be confused with or leak into buyer/store JWT auth) and renders: an MRR/status summary, a table of stores (status, snapshotted price, period end, an "Unlock" button when `locked`), and a plan-price form (current price + an input to set a new one, calling `POST /subscription/admin/plan-price`)
- `client/src/App.tsx`: `<Route path="/admin/billing" component={AdminBilling} />` — outside `StoreOwnerRoute`/`BuyerRoute` entirely, since neither JWT role applies; **not linked from `layout.tsx`'s nav** (reachable only by typing the URL), since it's an internal ops tool, not part of either customer-facing role
- Requests from this page attach `X-Admin-Token` directly (a small dedicated fetch helper, not `apiRequest` in `queryClient.ts`, since that wrapper is JWT-bearer-only and this page authenticates completely differently)

## 6. Error Handling

- Trial lapses with no Razorpay subscription ever created → `grace`, one email sent, owner can still complete checkout from `/billing` at any point during grace
- Payment fails mid-cycle (Razorpay reports `pending`/`halted`) → `grace`, same email, same recovery path
- Grace period expires unresolved → `locked`: `is_billing_locked=True`, store disappears from buyer browse/search, mutation endpoints 402, order-fulfillment endpoints keep working
- Payment succeeds at any point (including from `locked`) → `active`, `is_billing_locked=False`, no manual re-activation step needed
- Unverified/unsigned webhook request → `401`, logged, no state change (mirrors the delivery-dispatch webhook posture)
- Admin manual unlock (§3.5) bypasses Razorpay entirely — a support/goodwill path, not a substitute for real payment reconciliation; the next real webhook still updates state normally afterward

## 7. Implementation Order

1. Get a real Razorpay test/business account and confirm the actual Subscriptions API shape (plan/customer/subscription creation, Checkout integration, webhook event names and payload, signature verification) — resolve §3.4's "unverified" flag before writing code against the assumption
2. Backend: `Subscription` + `SubscriptionInvoice` entities + `Store.is_billing_locked` + migration + `models/db.py` registration
3. Backend: `RazorpayConfig` + `subscription_service.py` state machine + `assert_billing_ok()` + unit tests
4. Backend: hook trial creation into `StoreService.create_store()`
5. Backend: `POST /subscription/checkout` + `POST /subscription/webhook` (with a fake Razorpay client for tests) + `GET /subscription/status`
6. Backend: wire `assert_billing_ok()` into the mutation-path store dependencies listed in §5; filter `is_billing_locked` out of buyer-facing store queries
7. Backend: `POST /subscription/cancel` + admin endpoints (§3.5), including `GET`/`POST /subscription/admin/plan-price`
8. Frontend: `billing.tsx` + `/billing` route + Razorpay Checkout integration
9. Frontend: `use-subscription-status` hook + layout banner + nav link
10. Frontend: `queryClient.ts` 402 handling
11. Frontend: `admin-billing.tsx` + `/admin/billing` route + token-entry gate
12. End-to-end check: create a store (trial starts), let trial lapse in test data (or fast-forward `trial_end`), confirm grace email/banner, simulate a failed-then-succeeded webhook, confirm lock/unlock both propagate correctly to buyer visibility and owner mutation access; from `/admin/billing`, confirm a plan-price change is reflected on the next new store's checkout but not on an already-checked-out store's snapshotted price

## 8. Out of Scope (this version)

- Tiered/multiple plans, usage-based or GMV-percentage billing — single flat plan only, per the pricing decision
- Proration on cancel, upgrade/downgrade, or mid-cycle plan changes — an admin price change (§3.5) is deliberately not retroactive/prorated for existing subscribers, only applies going forward
- A general admin-user/RBAC system — `/admin/billing` (§5) reuses the existing single shared-secret `X-Admin-Token`, entered once and stored client-side; there's still no concept of individual admin accounts, permissions, or audit-by-whom beyond `SubscriptionPlan.created_by` defaulting to the string `"admin"`
- Hardening `/admin/billing`'s hosting/access beyond the shared-secret gate — **decided:** ships on the same domain as the public site (`groceror.store`, Netlify, catch-all SPA redirect already routes any path to `index.html`) rather than a separate host, since it's zero extra infra and this is still pre-revenue with one operator. The tradeoff accepted here: the page's code (exact endpoint shapes, what actions exist) ships in the same public bundle as the storefront, visible to anyone who loads the site and opens dev tools — the `X-Admin-Token` gate stops *use*, not *visibility*. Real gap, deliberately deferred: revisit (Netlify path-level access control, or moving admin behind something like Cloudflare Access) before this goes live with real Razorpay charges moving through it — same posture as the GST-invoicing and unverified-Razorpay-shape gaps above.
- A reminder email *sequence* during grace — one email on entering grace, no follow-ups, no SMS
- GST/tax-compliant invoicing — India B2B SaaS billing normally needs GST invoices; `SubscriptionInvoice` here is an internal payment record, not a compliant tax document. Real gap, deliberately deferred, should be revisited before this goes live commercially.
- Multi-store consolidated billing under one owner entity — each `Store` bills independently even if one entity owns several (§1); no bundling/discount for owning multiple stores
- Refunds
- Store Manager/Employee sub-roles interacting with billing — only the single `store`-role identity can view/manage billing, matching every other store-owner action today
- Confirming Razorpay's exact Subscriptions API shape, Checkout mandate-authorization behavior, and webhook signature scheme — flagged throughout §3.4 as assumed, not verified; blocks nothing in this design but is real implementation risk carried forward, same posture as Shiprocket Quick in `SPEC_DELIVERY_DISPATCH.md`
