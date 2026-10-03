# Orders module comment fixes

Source: https://app.notion.com/p/3e6eaf3778e1806c96e6d2788b7eb4fa

## Background and goal
Address the 14 review threads and the user's explicit instruction to comment out pickup. Existing drop-off persistence is already implemented. Keep unrelated edits isolated in separate backend/frontend worktrees.

## Current gaps and design
1. Pickup: comment out checkout selection and fallback; default to delivery even for older saved preferences. Retain historical order handling.
2. Location: distinguish geolocation failures from an unserviceable destination, enforce the store delivery radius, and discard stale delivery quotes when locations change.
3. Payment: the current card form only validates locally; no payment processor exists. Provide explicitly labelled demo wallet/card selections and preset test cards; never imply a charge, persist card credentials, or claim real saved-card support.
4. Recurring orders: remove the checkout controls from the MVP.
5. Inventory: refresh stock during cart/checkout and before submission; block missing or insufficient items. Keep authoritative stock validation with row locks and positive quantities on order creation.
6. Confirmation: confirm new orders automatically after stock is reserved. Keep packing and delivery transitions manual; a stock check cannot prove a parcel has been packed or delivered.
7. Alerts: show current order updates from order history on the Alerts page, including legacy pickup-ready orders, so an offline shopper can see the status on return.

## Data contracts
No new endpoints or database columns. Order creation returns confirmed instead of pending. Existing delivery quote errors use readable Location Unserviceable messages. Existing inventory browse and order history responses power stock checks and alerts.

## Implementation order and validation
Checkout MVP controls; location and quotes; payment stubs; stock and confirmation; alerts. Validate with focused API tests, TypeScript checking, production build, and Playwright checkout tests against isolated/local test services.

## Out of scope
Real payment processing, tokenized saved cards, automatic cross-store substitutions, removing exceptional cancellations, automatic packing/delivery, and deleting historical pickup orders. The two pickup workflow test observations do not require code changes. Default drop-off selection is already implemented and retained.

## Comment-by-comment disposition

| Thread | Result |
| --- | --- |
| Delivery location not picked up; show Location Unserviceable | Store radius checked before quote/order creation; readable error and stale-quote protection. |
| Remove pickup from India MVP | Pickup selector commented out; delivery default also overrides saved pickup preferences, per direct user instruction. |
| Remember default drop-off | Existing address/coordinate persistence retained; no repeated location request for a valid saved destination. |
| Apple Pay/G Pay block placing order | Explicit demo methods unblock workflow; no real payment is claimed. |
| Weekly/biweekly recurring controls are not MVP | Checkout scheduling controls removed. |
| Check stock before placing order, or suggest another store | Inventory refreshed every 15 seconds and on focus while open, plus a final submission check. Insufficient stock blocks checkout. Alternative-store sourcing not needed for the chosen option. |
| Store cancellation is a poor experience | Stock locking and automatic confirmation reduce avoidable cancellations; exceptional cancellation remains available because inventory alone cannot guarantee fulfillment. |
| Delivery only, repeated pickup comment | Covered by pickup disablement. |
| Detect card brand and preselect card | Visa and both Mastercard ranges recognised; preset test cards available. Real saved cards require a tokenizing payment provider and are deferred. |
| Automate order confirmation | New orders confirmed after stock reservation. |
| Shopper stuck unless logging into Sara's account | Separate manual store acceptance removed for new orders; packing and dispatch still require the store. |
| Tester marked order ready | Test observation; no standalone change. |
| Missing pickup-ready alert | Alerts page reads order history and refreshes, so ready status is visible even if its live event was missed. Historical pickup orders retained. |
| Tester marked order delivered; pickup workflow tested | Test observation; no standalone change. |

## Verification and limits

- Initial focused backend run: 165 passed; two additional integration regressions then passed in a 62-test order/delivery run.
- Browser regression coverage: 10 passed across the initial nine-test run and the additional stale-quote test.
- Frontend production build passed.
- Frontend type check hits the same pre-existing `server/vite.ts:42` allowedHosts typing error in both the original checkout and this worktree.
- Browser tests mock API responses; backend integration tests use SQLite and the fake delivery provider. PostgreSQL row-lock contention and live courier/payment integrations were not exercised.
- The existing Shiprocket adapter documents that its vendor API contract is unverified. Live service requires a configured and verified courier integration; no synthetic successful delivery quote was added.
