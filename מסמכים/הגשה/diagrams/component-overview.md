# דיאגרמת רכיבים: מבנה המערכת

```mermaid
flowchart TB
    subgraph CLIENT["צד לקוח: דפדפן"]
        direction TB
        pages["מסכים (Pages)"]
        comps["רכיבי ממשק (Components)"]
        api_client["שכבת הפנייה לשרת (API Layer)"]
        live["מנוי לעדכונים חיים"]
    end

    subgraph SERVER["צד שרת: שרת היישום"]
        direction TB
        controllers["שכבת הבקרים (Controllers)"]
        logic["שכבת השירותים (Services)"]
        entities["שכבת הישויות (Data Models)"]
        adapters["שכבת המתאמים (Adapters)"]
        wiring["מזריק תלויות (DI Container)"]
    end

    db[("מאגר הנתונים")]
    ai["שירות בינה מלאכותית<br/>חיצוני לארגון"]

    pages --> comps
    pages --> api_client
    pages --> live
    api_client -- "בקשה ותשובה" --> controllers
    controllers -- "הודעת רענון" --> live
    controllers --> logic
    logic --> entities
    logic --> adapters
    entities --> db
    adapters --> ai
    wiring -. "מרכיב ומזריק" .-> logic
    wiring -. "מרכיב ומזריק" .-> adapters
```

*מבנה המערכת: צד לקוח, צד שרת ומאגר הנתונים, יחד עם שירות הבינה המלאכותית החיצוני.
החצים הרציפים מסמנים בקשה ותשובה, החץ מן הבקרים אל מנוי העדכונים מסמן את הודעות הרענון
הנדחפות בערוץ החי, והחצים המקווקווים מסמנים בנייה והזרקה של תלויות על ידי מזריק התלויות.*
