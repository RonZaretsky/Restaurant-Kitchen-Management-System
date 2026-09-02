# דיאגרמת ER: הישויות והקשרים ביניהן

```mermaid
erDiagram
    USER ||--o{ ORDER : "פותח"
    USER ||--o{ ORDER_ITEM : "מכין"
    USER ||--o{ STOCK_MOVEMENT : "רושם"
    USER ||--o{ AI_RECIPE_SUGGESTION : "מבקש"
    USER ||--o{ AI_CHAT_SESSION : "מנהל"

    CATEGORY ||--o{ DISH : "מכילה"
    DISH ||--o{ RECIPE_INGREDIENT : "מורכבת מ"
    INGREDIENT ||--o{ RECIPE_INGREDIENT : "משמש ב"
    INGREDIENT ||--o{ STOCK_MOVEMENT : "מתועד ב"

    RESTAURANT_TABLE ||--o{ ORDER : "נושא"
    ORDER ||--o{ ORDER_ITEM : "מכילה"
    DISH ||--o{ ORDER_ITEM : "מוזמנת כ"

    AI_RECIPE_SUGGESTION ||--o| DISH : "אושרה למנה"
    AI_RECIPE_SUGGESTION ||--o{ AI_CHAT_SESSION : "נדונה ב"
    DISH ||--o{ AI_CHAT_SESSION : "נדונה ב"
    AI_CHAT_SESSION ||--o{ AI_CHAT_MESSAGE : "מכילה"

    USER {
        int id PK
        string username UK
        enum role
        bool is_active
    }

    CATEGORY {
        int id PK
        string name UK
    }

    DISH {
        int id PK
        int category_id FK
        bool is_available
        int source_suggestion_id FK "ייחודי"
    }

    INGREDIENT {
        int id PK
        string name UK
        enum unit
        decimal current_stock
        decimal min_stock_threshold
    }

    RECIPE_INGREDIENT {
        int dish_id PK "וגם זר"
        int ingredient_id PK "וגם זר"
        decimal quantity
    }

    RESTAURANT_TABLE {
        int id PK
        int table_number UK
        enum status
    }

    ORDER {
        int id PK
        int table_id FK
        int waiter_id FK
        enum status
        decimal total_amount
    }

    ORDER_ITEM {
        int id PK
        int order_id FK
        int dish_id FK
        int cook_id FK
        enum status
        decimal price_at_add
    }

    STOCK_MOVEMENT {
        int id PK
        int ingredient_id FK
        int performed_by FK
        enum movement_type
        decimal quantity_change
    }

    AI_RECIPE_SUGGESTION {
        int id PK
        int requested_by FK
        json generated_recipe
        bool dismissed
    }

    AI_CHAT_SESSION {
        int id PK
        int user_id FK
        int dish_id FK "אחד משניים"
        int suggestion_id FK "אחד משניים"
    }

    AI_CHAT_MESSAGE {
        int id PK
        int session_id FK
        enum role
    }
```

*הישויות והקשרים ביניהן. הדיאגרמה מציגה את המפתחות ואת השדות הנושאים משמעות לקשרים
בלבד, כדי שתישאר קריאה בגודל עמוד. הפירוט המלא של כל שדה נמצא בטבלאות שבסעיף 4.2.*
