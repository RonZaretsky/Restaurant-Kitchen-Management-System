# דיאגרמת מחלקות: מודול השף החכם

```mermaid
classDiagram
    direction TB

    class AIService {
        -logger
        -llmClient
        -_in_flight : set~int~
        -_chat_in_flight : set~int~
        -_suggestion_chat_in_flight : set~int~
        +generate_suggestion(db, actor, payload) AIRecipeSuggestionResponse
        +list_suggestions(db, actor) AIRecipeSuggestionResponse[]
        +dismiss_suggestion(db, actor, suggestion_id) AIRecipeSuggestionResponse
        +create_chat_session(db, actor, payload) AIChatSession
        +list_chat_sessions(db, actor) AIChatSessionResponse[]
        +list_chat_messages(db, actor, session_id) AIChatMessage[]
        +send_message(db, actor, session_id, payload) AIChatMessage
        -_build_prompt(ingredients, direction, prioritize_waste)$ str
        -_build_chat_system_message(target) str
        -_is_recipe_shape_valid(recipe)$ bool
        -_waste_risk_rank(ingredient)$ Decimal
        -_get_confirmed_dish_id(db, suggestion_id)$ int
    }

    class LLMClient {
        -client
        -model
        +generate_recipe(prompt) dict
        +send_chat_message(messages) str
        +send_chat_message_with_recipe_update(messages) dict
    }

    class AIRecipeSuggestion {
        +int id
        +int requested_by
        +str prompt_used
        +dict generated_recipe
        +dict ingredients_snapshot
        +bool dismissed
    }

    class AIChatSession {
        +int id
        +int user_id
        +str title
        +int dish_id
        +int suggestion_id
    }

    class AIChatMessage {
        +int id
        +int session_id
        +ChatRole role
        +str content
    }

    class ChatRole {
        <<enumeration>>
        user
        assistant
    }

    AIService ..> LLMClient : כל פנייה חיצונית דרכו
    AIService ..> AIRecipeSuggestion : יוצר ומעדכן
    AIService ..> AIChatSession : יוצר וקורא
    AIService ..> AIChatMessage : יוצר וקורא
    AIRecipeSuggestion "1" o-- "0..*" AIChatSession : נדונה ב
    AIChatSession "1" *-- "0..*" AIChatMessage : מכילה
    AIChatMessage ..> ChatRole
```

## הסבר המחלקות

1. **`LLMClient` הוא המקום היחיד במערכת שמכיר את הספק החיצוני.** ספריית הספק מיובאת בקובץ
   הזה ובו בלבד. `AIService` מכיר שלוש מתודות ולא מכיר ספק. החלפת ספק היא שינוי בקובץ אחד.

2. **שלוש המתודות של המתאם נבדלות בצורת התשובה, ולא בכוונה:**
   - `generate_recipe` מבקשת מסמך מובנה.
   - `send_chat_message` מבקשת טקסט חופשי, למקרה שבו `AIChatSession.dish_id` מוגדר.
   - `send_chat_message_with_recipe_update` מבקשת מסמך מובנה שמכיל גם תשובה וגם מתכון
     מעודכן, לשיחה סביב הצעה (`suggestion_id` מוגדר).

   הן מתודות נפרדות ולא הסתעפות בתוך מתודה אחת, כדי **שלכל אחת תהיה צורת תשובה אחת בלבד**.

3. **שלוש הרשימות הפרטיות הן שלוש מגבלות מקבילות שונות, ולא אחת משוכפלת:**

   | הרשימה | לפי מה | מה היא מונעת |
   |---|---|---|
   | `_in_flight` | טבח | בקשת הצעה שנייה של אותו טבח בזמן שהראשונה רצה |
   | `_chat_in_flight` | שיחה | שתי הודעות במקביל באותה שיחה, ששוברות את רצף השיחה |
   | `_suggestion_chat_in_flight` | הצעה | שתי שיחות שונות שמנסות לעדכן את אותה הצעה |

   הרשימה השלישית נדרשת מפני שהשנייה אינה מספיקה: שתי שיחות **שונות** יכולות להיות
   קשורות לאותה הצעה, ואז המגבלה לפי שיחה אינה חוסמת אותן.

   **הרשימות האלה הן הסיבה שהשירות הזה מוגדר כמופע יחיד** ולא נבנה מחדש בכל הזרקה. עותק
   חדש לכל בקשה היה מקבל רשימות ריקות, וכל שלוש המגבלות היו מפסיקות לעבוד **בשקט**.

4. **המתודות הסטטיות הן פונקציות טהורות.** בניית הפנייה, בדיקת צורת התשובה ודירוג הסיכון
   לבזבוז אינן תלויות במצב של השירות, ולכן ניתן לבדוק אותן בנפרד בלי שירות חיצוני ובלי
   מאגר.

5. **`_is_recipe_shape_valid` נקראת משני נתיבי כתיבה שונים**, יצירת הצעה ועדכון הצעה
   בשיחה. היא הוצאה למתודה משותפת בדיוק כדי ששני הנתיבים לא יתפצלו בהגדרה של "תשובה
   תקינה".

6. **אין שדה שמסמן שהצעה אושרה.** `_get_confirmed_dish_id` מחשבת זאת מהצד השני: היא בודקת
   אם קיימת מנה שמצביעה על ההצעה. אותה מתודה משמשת גם את הבדיקה שחוסמת אישור כפול וגם את
   הערך שמוחזר לתצוגה, כדי ששתיהן לא יוכלו להתפצל.

7. **הקשר בין שיחה להודעותיה הוא הרכבה**, והקשר בין הצעה לשיחות הוא צבירה.

8. **`dish_id` קיים במודל ובשירות, אך לא נגיש מהמסך.** `AIChatSession`/`AIService.send_message`
   תומכים בשיחה שתלויה במנה קיימת בתפריט לכל דבר, אבל שום מסך אינו יוצר שיחה כזו כיום -
   הפעולה "שיחת ייעוץ" היחידה שקיימת בפועל תמיד שולחת `suggestion_id`. זהו פער מכוון
   שמתועד כאן במפורש (באותה רוח שבה 7.8 מתעד את היעדרה של שכבת Repository), לא הסתרה
   שלו: מי שיחפש נתיב מסך לשיחה סביב מנה לא ימצא אחד.
