# Architecture

```mermaid
graph TD
    Client["Client\n(browser / app)"]

    subgraph groceror ["groceror (FastAPI :8000)"]
        UserAPI["auth & profile\n/user/*, /login (Google)"]
        StoreAPI["store & catalog\n/stores/* (incl. follow, feature), /products/*, /inventory/*"]
        CartOrderAPI["cart & orders\n/cart/*, /order/*, /coupons/*"]
        EngagementAPI["engagement & marketing\n/wishlist/*, /loyalty/*, /flash-sales/*,\n/price-alerts/*, /stock-alerts/*, /back-in-stock/*,\n/product-reviews/*, /bulk-rules/*, /scheduled-orders/*,\n/delivery-zones/*, /disputes/*"]
        DashboardAPI["dashboard & realtime\n/dashboard/*, /sse/*"]
    end

    PG[("PostgreSQL")]
    RMQ(["RabbitMQ"])

    subgraph consumers ["Companion Services"]
        GU["groceror-users"]
        GO["groceror-orders"]
        GE["groceror-email"]
    end

    UsersMongo[("MongoDB\n(users)")]
    OrdersMongo[("MongoDB\n(orders)")]
    Resend["Resend\n(email delivery)"]

    Client -->|HTTP| groceror
    groceror -->|read / write| PG
    UserAPI -->|user_events_queue| RMQ
    CartOrderAPI -->|order_queue| RMQ
    CartOrderAPI -->|email_queue| RMQ
    RMQ -->|user_events_queue| GU
    RMQ -->|order_queue| GO
    RMQ -->|email_queue| GE
    GU --> UsersMongo
    GO --> OrdersMongo
    GE --> Resend
```

`main.py` registers ~23 routers total (`api/*_api.py`); the diagram groups them by concern rather than listing each one. `api/firebase_api.py` exists but is commented out in `main.py` (not currently mounted).
