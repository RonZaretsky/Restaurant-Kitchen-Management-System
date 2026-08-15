# Database Schema — Restaurant Kitchen Management System

## Overview

The database is divided into 5 functional modules + AI features, implemented with SQLAlchemy ORM on top of a relational database (PostgreSQL recommended).

---

## Module 1: User Management

### `User`
Central table for all system users. Role-based access controls which screens and actions each user can perform.

| Column | Type | Constraints | Description |
|---|---|---|---|
| id | INT | PK, auto-increment | Unique user identifier |
| username | VARCHAR(50) | NOT NULL, UNIQUE | Login username |
| password_hash | VARCHAR(255) | NOT NULL | Bcrypt-hashed password |
| full_name | VARCHAR(100) | NOT NULL | Display name |
| role | ENUM | NOT NULL | `admin` / `waiter` / `cook` / `warehouse_manager` |
| is_active | BOOLEAN | NOT NULL, default TRUE | Soft-delete / deactivation flag |
| created_at | TIMESTAMP | NOT NULL, default NOW() | Account creation time |

**Role permissions summary:**
- `admin` — full access: menu, users, reports, inventory
- `waiter` — open tables, create/view orders
- `cook` — view incoming orders, update item status
- `warehouse_manager` — view/update inventory, receive stock movements alerts

---

## Module 2: Menu Management

### `Category`
Groups dishes into logical sections (e.g. Starters, Mains, Desserts, Drinks).

| Column | Type | Constraints | Description |
|---|---|---|---|
| id | INT | PK, auto-increment | Unique category identifier |
| name | VARCHAR(50) | NOT NULL, UNIQUE | Category display name |

### `Dish`
Represents a single item on the restaurant menu.

| Column | Type | Constraints | Description |
|---|---|---|---|
| id | INT | PK, auto-increment | Unique dish identifier |
| name | VARCHAR(100) | NOT NULL | Dish display name |
| description | TEXT | nullable | Full description shown to waiters/customers |
| price | DECIMAL(8,2) | NOT NULL | Current price in local currency |
| category_id | INT | FK → Category.id, NOT NULL | Menu category |
| is_available | BOOLEAN | NOT NULL, default FALSE | Can the dish be ordered right now |
| prep_time_minutes | INT | nullable | Estimated kitchen preparation time |
| image_url | VARCHAR(255) | nullable | Path or URL to dish photo |
| created_at | TIMESTAMP | NOT NULL, default NOW() | When dish was added to menu |

**Relationships:** `Category` 1 → ∞ `Dish`

---

## Module 3: Recipe & Ingredients

### `Ingredient`
Raw material tracked in inventory. Stock is updated automatically when orders are placed.

| Column | Type | Constraints | Description |
|---|---|---|---|
| id | INT | PK, auto-increment | Unique ingredient identifier |
| name | VARCHAR(100) | NOT NULL, UNIQUE | Ingredient name (e.g. "Tomato", "Olive Oil") |
| unit | ENUM | NOT NULL | `kg` / `liter` / `piece` |
| current_stock | DECIMAL(10,3) | NOT NULL, default 0 | Current quantity in stock |
| min_stock_threshold | DECIMAL(10,3) | NOT NULL | Minimum before low-stock alert fires |
| created_at | TIMESTAMP | NOT NULL, default NOW() | When ingredient was registered |
| updated_at | TIMESTAMP | NOT NULL, default NOW() | Last time stock or details were modified |

### `RecipeIngredient` (junction table)
Defines which ingredients and in what quantities are required to prepare a dish. This is the M:N bridge between `Dish` and `Ingredient`.

| Column | Type | Constraints | Description |
|---|---|---|---|
| dish_id | INT | PK, FK → Dish.id | The dish this recipe line belongs to |
| ingredient_id | INT | PK, FK → Ingredient.id | The ingredient required |
| unit | ENUM | NOT NULL | `kg` / `liter` / `piece` — may differ from ingredient's base unit |
| quantity | DECIMAL(10,3) | NOT NULL | Amount needed per single serving |

**Relationships:** `Dish` 1 → ∞ `RecipeIngredient` ← ∞ : 1 `Ingredient`

**Business logic:** When an `OrderItem` is marked as `in_preparation`, the system deducts `quantity × order_item.quantity` from `Ingredient.current_stock` and creates a `StockMovement` record of type `consumption`.

---

## Module 4: Table & Order Management

### `RestaurantTable`
Physical tables in the restaurant.

| Column | Type | Constraints | Description |
|---|---|---|---|
| id | INT | PK, auto-increment | Unique table identifier |
| table_number | INT | NOT NULL, UNIQUE | Human-readable table number |
| capacity | INT | NOT NULL | Maximum number of diners |
| status | ENUM | NOT NULL, default `available` | `available` / `occupied` / `reserved` |

### `Order`
Represents a single customer session at a table. Created when a waiter opens the table; closed when bill is paid.

| Column | Type | Constraints | Description |
|---|---|---|---|
| id | INT | PK, auto-increment | Unique order identifier |
| table_id | INT | FK → RestaurantTable.id, NOT NULL | Which table this order belongs to |
| waiter_id | INT | FK → User.id, NOT NULL | Waiter who opened the order |
| status | ENUM | NOT NULL, default `pending` | `pending` → `in_preparation` → `ready` → `served` → `closed` |
| created_at | TIMESTAMP | NOT NULL, default NOW() | When the order was opened |
| closed_at | TIMESTAMP | nullable | When the bill was paid / order closed |
| total_amount | DECIMAL(10,2) | nullable | Calculated total; populated on close |

**Status lifecycle:**
```
pending → in_preparation → ready → served → closed
```
Order status is derived from its items: once any item moves to `in_preparation`, the order follows. When all items are `ready`, the order becomes `ready`.

### `OrderItem`
A single dish line within an order. Each item can be tracked and cooked independently.

| Column | Type | Constraints | Description |
|---|---|---|---|
| id | INT | PK, auto-increment | Unique order item identifier |
| order_id | INT | FK → Order.id, NOT NULL | Parent order |
| dish_id | INT | FK → Dish.id, NOT NULL | Which dish was ordered |
| quantity | INT | NOT NULL, default 1 | How many portions |
| status | ENUM | NOT NULL, default `pending` | `pending` / `in_preparation` / `ready` |
| notes | TEXT | nullable | Special requests from customer (e.g. "no onions") |
| cook_id | INT | FK → User.id, nullable | Cook who picked up and is preparing this item |
| price_at_add | NUMERIC(8,2) | NOT NULL | The Dish's price at the moment this item was added (AD-7). Order totals are always summed from this, never from a live `Dish.price` lookup, so a later price change never alters an already-open order. |

**Relationships:**
- `Order` 1 → ∞ `OrderItem`
- `Dish` 1 → ∞ `OrderItem`
- `User` (cook) 1 → ∞ `OrderItem` (optional)

---

## Module 5: Inventory

### `StockMovement`
Append-only log of every change to ingredient stock. Provides a full audit trail.

| Column | Type | Constraints | Description |
|---|---|---|---|
| id | INT | PK, auto-increment | Unique movement identifier |
| ingredient_id | INT | FK → Ingredient.id, NOT NULL | Which ingredient changed |
| movement_type | ENUM | NOT NULL | `purchase` / `consumption` / `waste` / `adjustment` |
| quantity_change | DECIMAL(10,3) | NOT NULL | Positive = stock added, negative = stock removed |
| reference_id | INT | nullable | If `consumption`: links to the `Order.id` that caused it |
| performed_by | INT | FK → User.id, NOT NULL | User who logged this movement |
| timestamp | TIMESTAMP | NOT NULL, default NOW() | When the movement occurred |
| notes | TEXT | nullable | Optional reason / comment |

**Movement types:**
| Type | Who | When |
|---|---|---|
| `purchase` | warehouse_manager | New stock delivered |
| `consumption` | system (automatic) | Order item moves to `in_preparation` |
| `waste` | warehouse_manager / cook | Ingredient disposed |
| `adjustment` | warehouse_manager | Manual stock correction |

**Alert logic:** After every `consumption` movement, the system checks if `Ingredient.current_stock < min_stock_threshold`. If so, it notifies the warehouse manager.

---

## Module 6: AI Features

### `AIRecipeSuggestion`
Stores every AI-generated recipe suggestion. Snapshots the current stock so suggestions can be audited and reproduced.

| Column | Type | Constraints | Description |
|---|---|---|---|
| id | INT | PK, auto-increment | Unique suggestion identifier |
| requested_by | INT | FK → User.id, NOT NULL | Chef/admin who requested the suggestion |
| prompt_used | TEXT | NOT NULL | The exact prompt sent to OpenAI |
| generated_recipe | JSON | NOT NULL | Full structured recipe returned by AI |
| ingredients_snapshot | JSON | NOT NULL | Snapshot of current stock at time of request |
| created_at | TIMESTAMP | NOT NULL, default NOW() | Request time |

### `AIChatSession`
Groups a series of messages in a single chat conversation between a user and the AI assistant.

| Column | Type | Constraints | Description |
|---|---|---|---|
| id | INT | PK, auto-increment | Unique session identifier |
| user_id | INT | FK → User.id, NOT NULL | Who owns this session |
| title | VARCHAR(200) | NOT NULL | Auto-generated or user-defined session title |
| created_at | TIMESTAMP | NOT NULL, default NOW() | When the session started |

### `AIChatMessage`
A single message within an AI chat session.

| Column | Type | Constraints | Description |
|---|---|---|---|
| id | INT | PK, auto-increment | Unique message identifier |
| session_id | INT | FK → AIChatSession.id, NOT NULL | Parent session |
| role | ENUM | NOT NULL | `user` / `assistant` |
| content | TEXT | NOT NULL | Message body |
| created_at | TIMESTAMP | NOT NULL, default NOW() | Message timestamp |

**Relationships:** `AIChatSession` 1 → ∞ `AIChatMessage`

---

## Relationship Summary

| From | To | Type | Via |
|---|---|---|---|
| Category | Dish | 1 : ∞ | `Dish.category_id` |
| Dish | RecipeIngredient | 1 : ∞ | `RecipeIngredient.dish_id` |
| Ingredient | RecipeIngredient | 1 : ∞ | `RecipeIngredient.ingredient_id` |
| RestaurantTable | Order | 1 : ∞ | `Order.table_id` |
| User (waiter) | Order | 1 : ∞ | `Order.waiter_id` |
| Order | OrderItem | 1 : ∞ | `OrderItem.order_id` |
| Dish | OrderItem | 1 : ∞ | `OrderItem.dish_id` |
| User (cook) | OrderItem | 1 : ∞ (optional) | `OrderItem.cook_id` |
| Ingredient | StockMovement | 1 : ∞ | `StockMovement.ingredient_id` |
| User | StockMovement | 1 : ∞ | `StockMovement.performed_by` |
| User | AIRecipeSuggestion | 1 : ∞ | `AIRecipeSuggestion.requested_by` |
| User | AIChatSession | 1 : ∞ | `AIChatSession.user_id` |
| AIChatSession | AIChatMessage | 1 : ∞ | `AIChatMessage.session_id` |
