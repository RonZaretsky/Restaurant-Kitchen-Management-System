# דיאגרמת מחלקות: מודול התפריט

```mermaid
classDiagram
    direction TB

    class MenuService {
        -logger
        +create_category(db, actor, payload) Category
        +list_categories(db) Category[]
        +create_dish(db, actor, payload) Dish
        +list_dishes(db) Dish[]
        +get_dish(db, actor, dish_id) Dish
        +update_dish(db, actor, dish_id, payload) Dish
        +list_recipe_ingredients(db, actor, dish_id) RecipeIngredient[]
        +add_recipe_ingredient(db, actor, dish_id, payload) RecipeIngredient
        +update_recipe_ingredient(db, actor, dish_id, ingredient_id, payload) RecipeIngredient
        +remove_recipe_ingredient(db, actor, dish_id, ingredient_id)
        -_lock_dish(db, dish_id) Dish
        -_reject_if_recipe_empty(db, dish, actor)
        -_reject_if_unit_mismatched(recipe_unit, ingredient)
        -_validate_source_suggestion(db, actor, suggestion_id)
        -_get_category(db, actor, category_id) Category
        -_get_ingredient(db, actor, ingredient_id) Ingredient
        -_get_recipe_ingredient(db, dish_id, ingredient_id) RecipeIngredient
    }

    class Category {
        +int id
        +str name
    }

    class Dish {
        +int id
        +str name
        +Decimal price
        +int category_id
        +bool is_available
        +int source_suggestion_id
    }

    class RecipeIngredient {
        +int dish_id
        +int ingredient_id
        +Decimal quantity
        +Unit unit
    }

    class Ingredient {
        +int id
        +str name
        +Unit unit
        +bool is_active
    }

    MenuService ..> Category : יוצר וקורא
    MenuService ..> Dish : יוצר, קורא ומעדכן
    MenuService ..> RecipeIngredient : מנהל
    MenuService ..> Ingredient : מאמת מולו יחידות
    Category "1" --> "0..*" Dish : מקבצת
    Dish "1" *-- "0..*" RecipeIngredient : מורכבת מ
    Ingredient "1" --> "0..*" RecipeIngredient : משמש ב
```

## הסבר המחלקות

1. **שלוש מהמתודות הפרטיות הן שומרות סף, ולא עזרי נוחות.** הן קיימות כדי שכלל עסקי ייכתב
   פעם אחת ויישמר משני כיוונים:

   - `_reject_if_recipe_empty` נקראת **גם** בעת סימון מנה כזמינה **וגם** בעת הסרת שורת
     מתכון. אלה שני כיוונים לאותו כלל: מנה זמינה חייבת מתכון. בלי המתודה המשותפת, אפשר
     היה לתקן כיוון אחד ולשכוח את השני.
   - `_reject_if_unit_mismatched` אוכפת שיחידת המידה בשורת המתכון זהה ליחידת המרכיב.
     המערכת אינה ממירה בין יחידות, ואי-התאמה הייתה מנכה כמות שגויה **בלי הודעת שגיאה**.
   - `_validate_source_suggestion` מוודאת שההצעה קיימת, לא נדחתה ולא אושרה כבר.

2. **`_lock_dish` נועלת את המנה בשני הכיוונים של הכלל.** סימון כזמינה והסרת השורה האחרונה
   הן פעולות שיכולות להתרחש במקביל, ובלי הנעילה שתיהן היו יכולות להצליח יחד ולהשאיר מנה
   זמינה בלי מתכון.

3. **יצירת מנה היא הנתיב היחיד שבו הצעת מתכון הופכת למנה.** אין מתודת "אשר הצעה" נפרדת:
   האישור הוא יצירת מנה שנושאת הפניה להצעה. **הבדיקה המקדימה יכולה להפסיד מרוץ לשתי
   יצירות מקבילות, ולכן האכיפה האמיתית היא אילוץ הייחודיות במבנה**, וההתנגשות שנוצרת ממנו
   מתורגמת לשגיאה מנומקת ולא לתקלת שרת.

4. **הקשר בין מנה לשורות המתכון הוא הרכבה** (מעוין מלא): שורת מתכון אינה קיימת בלי המנה
   שלה. לעומת זאת **הקשר מהמרכיב לשורת המתכון הוא שיוך רגיל**: המרכיב קיים בזכות עצמו
   ומשמש מנות רבות.

5. **קטגוריות ניתנות ליצירה ולקריאה בלבד** בגרסה זו. אין עריכה ואין מחיקה, בהתאם לכלל
   שאין מחיקה במערכת.
