# Product Catalog API — Spec

## Background

The frontend `/products` page currently renders a **hardcoded static catalog** of 17 items in `catalog.ts`. This spec replaces that with a live backend-driven catalog stored in the database.

---

## Data Model — new `Product` table

```
Product
  id            UUID        PK, auto-generated
  name          str         unique, indexed
  category      enum        GROCERY | PRODUCE | MEAT | DAIRY | BAKERY | OTHER
  image_url     str         optional — Unsplash URL or similar
  default_price float       suggested retail price
  created_at    datetime    auto
  updated_at    datetime    auto
```

This is a master catalog table — distinct from `Inventory` (which is a store's instance of a product with their own price and quantity).

---

## Endpoints

### `GET /products`
Returns the full product catalog. **No auth required** — buyers and store owners both see this.

**Response**
```json
{
  "products": [
    {
      "id": "uuid",
      "name": "Bananas",
      "category": "PRODUCE",
      "image_url": "https://...",
      "default_price": 1.29
    }
  ]
}
```

Optional query params:
- `?category=PRODUCE` — filter by category
- `?q=ban` — search by name (min 2 chars)

---

### `POST /products`
Add a new product to the catalog. **Auth required — store owners only.**

**Request body**
```json
{
  "name": "Bananas",
  "category": "PRODUCE",
  "image_url": "https://...",
  "default_price": 1.29
}
```

**Response**
```json
{ "product_id": "uuid" }
```

Returns `409 Conflict` if a product with the same name already exists.

---

### `GET /products/{product_id}`
Fetch a single product by ID. **No auth required.**

**Response** — same shape as a single item from `GET /products`.

---

## Seeding

The 17 items currently in `catalog.ts` should be seeded into the `Product` table on first migration. These are the source of truth:

| Name | Category | Default Price |
|---|---|---|
| Bananas | PRODUCE | 1.29 |
| Carrots | PRODUCE | 0.99 |
| Avocado | PRODUCE | 1.49 |
| Tomatoes | PRODUCE | 2.49 |
| Sourdough Bread | BAKERY | 4.99 |
| Croissants | BAKERY | 3.49 |
| Whole Milk | DAIRY | 3.29 |
| Cheddar Cheese | DAIRY | 5.49 |
| Greek Yogurt | DAIRY | 2.99 |
| Chicken Breast | MEAT | 7.99 |
| Salmon Fillet | MEAT | 12.99 |
| Penne Pasta | GROCERY | 1.79 |
| Jasmine Rice | GROCERY | 3.49 |
| Olive Oil | GROCERY | 8.99 |
| Orange Juice | GROCERY | 4.29 |
| Honey | OTHER | 6.99 |
| Dark Chocolate | OTHER | 3.99 |

Image URLs can be carried over from `catalog.ts` verbatim.

---

## Frontend changes needed (for FE team)

1. **Replace static import** — `catalog.ts` `CATALOG` array is no longer the source of truth. Replace with a `useQuery` call to `GET /products`.

2. **New query key** — `["/products"]`

3. **Type change** — `CatalogItem` gains an `id: string` field (the UUID from the backend). This is needed when calling `POST /inventory/add-inventory` so the backend can optionally link inventory items back to a catalog product in the future.

4. **Category filter** — can pass `?category=<ENUM>` instead of client-side filtering, or keep client-side — either works since the dataset is small.

5. **No auth token needed** for `GET /products` — the fetch should be unauthenticated (unlike most other API calls).

---

## Out of scope for this iteration

- Admin-only product management / approval flow
- Product images hosted on the backend (Unsplash URLs are fine for now)
- Linking `Inventory.product_id` back to `Product` (no FK added to Inventory yet)
- Pagination (17 → low hundreds is fine without it)
