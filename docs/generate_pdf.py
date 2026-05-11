"""Generate Hebrew RTL PDF documentation for the database schema."""
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_RIGHT, TA_CENTER
from bidi.algorithm import get_display

FONT_PATH = "/Library/Fonts/Arial Unicode.ttf"
pdfmetrics.registerFont(TTFont("ArialUnicode", FONT_PATH))

OUTPUT = "database-schema-he.pdf"
PAGE_W, PAGE_H = A4

doc = SimpleDocTemplate(
    OUTPUT,
    pagesize=A4,
    rightMargin=2 * cm,
    leftMargin=2 * cm,
    topMargin=2 * cm,
    bottomMargin=2 * cm,
)

# ── Styles ──────────────────────────────────────────────────────────────────
FONT = "ArialUnicode"

def style(name, size, bold=False, color=colors.black, align=TA_RIGHT,
          space_before=0, space_after=4):
    return ParagraphStyle(
        name,
        fontName=FONT,
        fontSize=size,
        textColor=color,
        alignment=align,
        spaceAfter=space_after,
        spaceBefore=space_before,
        leading=size * 1.45,
    )

s_title    = style("title",    22, align=TA_CENTER,
                   color=colors.HexColor("#1a3c6e"), space_before=10, space_after=6)
s_subtitle = style("subtitle", 12, align=TA_CENTER,
                   color=colors.HexColor("#555555"), space_after=14)
s_module   = style("module",   15, color=colors.HexColor("#1a3c6e"), space_before=18, space_after=6)
s_table    = style("table",    13, color=colors.HexColor("#2d6a2d"), space_before=10, space_after=4)
s_body     = style("body",     11, space_after=4)
s_note     = style("note",     10, color=colors.HexColor("#555555"), space_after=4)
s_th       = style("th",        9, color=colors.white, align=TA_CENTER, space_after=0)
s_td_c     = style("td_c",      9, align=TA_CENTER, space_after=0)
s_td_r     = style("td_r",      9, align=TA_RIGHT,  space_after=0)

HDR_BG  = colors.HexColor("#1a3c6e")
ROW_ALT = colors.HexColor("#eef3fb")
ROW_NRM = colors.white
BORDER  = colors.HexColor("#b0b8cc")

def hr():
    return HRFlowable(width="100%", thickness=1, color=colors.HexColor("#cccccc"),
                      spaceAfter=4, spaceBefore=4)

def h(text):
    """Apply bidi algorithm so Hebrew renders correctly in reportlab."""
    return get_display(str(text))

def p(text, st=None):
    return Paragraph(h(text), st or s_body)

def section(title):
    return [p(title, s_module), hr()]

def table_heading(name, desc=""):
    parts = [Paragraph(h(f"טבלה: {name}"), s_table)]
    if desc:
        parts.append(Paragraph(h(desc), s_note))
    return parts

def col_table(rows, col_names=None):
    if col_names is None:
        col_names = ["עמודה", "סוג", "אילוצים", "תיאור"]
    header = [Paragraph(h(c), s_th) for c in col_names]
    data = [header]
    for i, row in enumerate(rows):
        bg = ROW_ALT if i % 2 else ROW_NRM
        data.append([Paragraph(h(str(cell)), s_td_r if j == 0 else s_td_c)
                      for j, cell in enumerate(row)])

    col_widths = [4.5*cm, 3.5*cm, 4.5*cm, 5.5*cm]
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), HDR_BG),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [ROW_NRM, ROW_ALT]),
        ("GRID",          (0, 0), (-1, -1), 0.4, BORDER),
        ("FONTNAME",      (0, 0), (-1, -1), FONT),
        ("FONTSIZE",      (0, 0), (-1, -1), 9),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 5),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
    ]))
    return t


# ── Content ──────────────────────────────────────────────────────────────────
story = []

# Title
story += [
    p("מערכת לניהול מטבח של מסעדה", s_title),
    p("תיעוד סכמת מסד הנתונים", s_subtitle),
    hr(), Spacer(1, 8),
]

# ── Overview ─────────────────────────────────────────────────────────────────
story += section("סקירה כללית")
story += [
    p("מסד הנתונים מחולק ל-5 מודולים פונקציונליים בתוספת מודול בינה מלאכותית. "
      "המימוש נעשה עם SQLAlchemy ORM על גבי PostgreSQL."),
    Spacer(1, 4),
]

overview_rows = [
    ["ניהול משתמשים",  "User"],
    ["ניהול תפריט",    "Category, Dish"],
    ["מתכונים ומלאי",  "Ingredient, RecipeIngredient"],
    ["שולחנות והזמנות","RestaurantTable, Order, OrderItem"],
    ["לוגיסטיקה",      "StockMovement"],
    ["בינה מלאכותית",  "AIRecipeSuggestion, AIChatSession, AIChatMessage"],
]
story.append(col_table(overview_rows, ["מודול", "טבלאות"]))
story.append(Spacer(1, 10))

# ── Module 1: Users ───────────────────────────────────────────────────────────
story += section("מודול 1 — ניהול משתמשים")
story += table_heading("User", "טבלה מרכזית לכל משתמשי המערכת. הרשאות נקבעות לפי תפקיד (role).")
story.append(col_table([
    ["id",            "INT",            "PK, Auto-increment", "מזהה ייחודי"],
    ["username",      "VARCHAR(50)",    "NOT NULL, UNIQUE",   "שם משתמש לכניסה"],
    ["password_hash", "VARCHAR(255)",   "NOT NULL",           "סיסמה מוצפנת (Bcrypt)"],
    ["full_name",     "VARCHAR(100)",   "NOT NULL",           "שם מלא לתצוגה"],
    ["role",          "ENUM",           "NOT NULL",           "admin / waiter / cook / warehouse_manager"],
    ["is_active",     "BOOLEAN",        "default TRUE",       "כיבוי/הפעלה של חשבון"],
    ["created_at",    "TIMESTAMP",      "default NOW()",      "מועד יצירת החשבון"],
]))
story.append(p("סיכום הרשאות לפי תפקיד:", s_note))
story.append(col_table([
    ["admin",             "גישה מלאה: תפריט, משתמשים, דוחות, מלאי"],
    ["waiter",            "פתיחת שולחן, יצירה וצפייה בהזמנות"],
    ["cook",              "צפייה בהזמנות נכנסות, עדכון סטטוס פריטים"],
    ["warehouse_manager", "עדכון מלאי, קבלת התראות על חוסרים"],
], ["תפקיד", "הרשאות"]))

# ── Module 2: Menu ────────────────────────────────────────────────────────────
story += section("מודול 2 — ניהול תפריט")

story += table_heading("Category", "קיבוץ מנות לקטגוריות (למשל: ראשונות, עיקריות, קינוחים, משקאות).")
story.append(col_table([
    ["id",   "INT",         "PK, Auto-increment", "מזהה ייחודי"],
    ["name", "VARCHAR(50)", "NOT NULL, UNIQUE",   "שם הקטגוריה"],
]))
story.append(Spacer(1, 6))

story += table_heading("Dish", "מנה בודדת בתפריט המסעדה.")
story.append(col_table([
    ["id",                "INT",           "PK, Auto-increment", "מזהה ייחודי"],
    ["name",              "VARCHAR(100)",  "NOT NULL",           "שם המנה"],
    ["description",       "TEXT",          "nullable",           "תיאור מלא"],
    ["price",             "DECIMAL(8,2)",  "NOT NULL",           "מחיר נוכחי"],
    ["category_id",       "INT",           "FK → Category",      "קטגוריה"],
    ["is_available",      "BOOLEAN",       "default TRUE",       "האם ניתן להזמין כרגע"],
    ["prep_time_minutes", "INT",           "nullable",           "זמן הכנה משוער (דקות)"],
    ["image_url",         "VARCHAR(255)",  "nullable",           "נתיב/URL לתמונת המנה"],
    ["created_at",        "TIMESTAMP",     "default NOW()",      "מועד הוספה לתפריט"],
]))
story.append(p("קשר: Category 1 → ∞ Dish", s_note))

# ── Module 3: Recipe ──────────────────────────────────────────────────────────
story += section("מודול 3 — מתכונים וחומרי גלם")

story += table_heading("Ingredient", "חומר גלם הנמצא במעקב מלאי. המלאי מתעדכן אוטומטית עם הזמנת מנות.")
story.append(col_table([
    ["id",                  "INT",            "PK, Auto-increment", "מזהה ייחודי"],
    ["name",                "VARCHAR(100)",   "NOT NULL, UNIQUE",   "שם חומר הגלם"],
    ["unit",                "ENUM",           "NOT NULL",           "kg / liter / piece"],
    ["current_stock",       "DECIMAL(10,3)",  "default 0",          "כמות נוכחית במלאי"],
    ["min_stock_threshold", "DECIMAL(10,3)",  "NOT NULL",           "מינימום לפני התראת חוסר"],
    ["created_at",          "TIMESTAMP",      "default NOW()",      "מועד רישום"],
    ["updated_at",          "TIMESTAMP",      "default NOW()",      "מועד עדכון אחרון (מלאי / פרטים)"],
]))
story.append(Spacer(1, 6))

story += table_heading("RecipeIngredient",
    "טבלת גשר (M:N) בין Dish ל-Ingredient. מגדירה את הכמות הנדרשת מכל מרכיב להכנת מנה.")
story.append(col_table([
    ["dish_id",       "INT",           "PK, FK → Dish",       "המנה שהמתכון שייך אליה"],
    ["ingredient_id", "INT",           "PK, FK → Ingredient", "חומר הגלם הנדרש"],
    ["unit",          "ENUM",          "NOT NULL",            "kg / liter / piece"],
    ["quantity",      "DECIMAL(10,3)", "NOT NULL",            "כמות לפורציה אחת"],
]))
story.append(p(
    "לוגיקה עסקית: כאשר OrderItem עובר לסטטוס in_preparation, המערכת מנכה "
    "quantity × order_item.quantity מ-Ingredient.current_stock ויוצרת רשומת StockMovement מסוג consumption.",
    s_note))

# ── Module 4: Orders ──────────────────────────────────────────────────────────
story += section("מודול 4 — שולחנות והזמנות")

story += table_heading("RestaurantTable", "שולחן פיזי במסעדה.")
story.append(col_table([
    ["id",           "INT",  "PK, Auto-increment", "מזהה ייחודי"],
    ["table_number", "INT",  "NOT NULL, UNIQUE",   "מספר שולחן קריא לאדם"],
    ["capacity",     "INT",  "NOT NULL",           "מספר סועדים מקסימלי"],
    ["status",       "ENUM", "default available",  "available / occupied / reserved"],
]))
story.append(Spacer(1, 6))

story += table_heading("Order", "הזמנה פתוחה לשולחן. נוצרת עם פתיחת השולחן, נסגרת עם תשלום.")
story.append(col_table([
    ["id",           "INT",           "PK, Auto-increment",  "מזהה ייחודי"],
    ["table_id",     "INT",           "FK → RestaurantTable","שולחן ההזמנה"],
    ["waiter_id",    "INT",           "FK → User",           "מלצר שפתח"],
    ["status",       "ENUM",          "default pending",     "pending→in_preparation→ready→served→closed"],
    ["created_at",   "TIMESTAMP",     "default NOW()",       "פתיחת ההזמנה"],
    ["closed_at",    "TIMESTAMP",     "nullable",            "סגירת ההזמנה / תשלום"],
    ["total_amount", "DECIMAL(10,2)", "nullable",            "סכום כולל (מחושב בסגירה)"],
]))
story.append(Spacer(1, 6))

story += table_heading("OrderItem", "שורת מנה בתוך הזמנה. כל פריט נעקב ומבושל באופן עצמאי.")
story.append(col_table([
    ["id",       "INT",  "PK, Auto-increment",   "מזהה ייחודי"],
    ["order_id", "INT",  "FK → Order, NOT NULL", "ההזמנה האם"],
    ["dish_id",  "INT",  "FK → Dish, NOT NULL",  "המנה שהוזמנה"],
    ["quantity", "INT",  "NOT NULL, default 1",  "כמה פורציות"],
    ["status",   "ENUM", "default pending",      "pending / in_preparation / ready"],
    ["notes",    "TEXT", "nullable",             "בקשות מיוחדות (למשל: 'ללא בצל')"],
    ["cook_id",  "INT",  "FK → User, nullable",  "הטבח המטפל בפריט זה"],
]))

# ── Module 5: Inventory ───────────────────────────────────────────────────────
story += section("מודול 5 — מלאי ולוגיסטיקה")

story += table_heading("StockMovement",
    "יומן שינויים במלאי — Append-only. מספק מסלול ביקורת מלא לכל שינוי בחומרי הגלם.")
story.append(col_table([
    ["id",             "INT",           "PK, Auto-increment",    "מזהה ייחודי"],
    ["ingredient_id",  "INT",           "FK → Ingredient",       "חומר הגלם שהשתנה"],
    ["movement_type",  "ENUM",          "NOT NULL",              "purchase/consumption/waste/adjustment"],
    ["quantity_change","DECIMAL(10,3)", "NOT NULL",              "חיובי=הוסף, שלילי=הוציא"],
    ["reference_id",   "INT",           "nullable",              "אם consumption: מזהה ה-Order"],
    ["performed_by",   "INT",           "FK → User",             "מי ביצע את השינוי"],
    ["timestamp",      "TIMESTAMP",     "default NOW()",         "מועד השינוי"],
    ["notes",          "TEXT",          "nullable",              "סיבה / הערה"],
]))
story.append(col_table([
    ["purchase",    "warehouse_manager", "קליטת סחורה חדשה"],
    ["consumption", "מערכת (אוטומטי)", "בעת הכנת מנה"],
    ["waste",       "warehouse_manager / cook", "השלכת חומר גלם"],
    ["adjustment",  "warehouse_manager", "תיקון ידני של מלאי"],
], ["סוג תנועה", "מי מבצע", "מתי"]))
story.append(p(
    "לוגיקת התראות: לאחר כל תנועת consumption, המערכת בודקת אם "
    "Ingredient.current_stock < min_stock_threshold — אם כן, נשלחת התראה למנהל המחסן.",
    s_note))

# ── Module 6: AI ──────────────────────────────────────────────────────────────
story += section("מודול 6 — בינה מלאכותית (AI Features)")

story += table_heading("AIRecipeSuggestion",
    "שמירת כל הצעת מתכון שנוצרה על ידי AI. כולל snapshot של המלאי לצורך ביקורת ושחזור.")
story.append(col_table([
    ["id",                   "INT",       "PK, Auto-increment", "מזהה ייחודי"],
    ["requested_by",         "INT",       "FK → User",          "שף/מנהל שביקש הצעה"],
    ["prompt_used",          "TEXT",      "NOT NULL",           "הפרומפט שנשלח ל-OpenAI"],
    ["generated_recipe",     "JSON",      "NOT NULL",           "המתכון המובנה שהוחזר"],
    ["ingredients_snapshot", "JSON",      "NOT NULL",           "מצב המלאי בזמן הבקשה"],
    ["created_at",           "TIMESTAMP", "default NOW()",      "זמן הבקשה"],
]))
story.append(Spacer(1, 6))

story += table_heading("AIChatSession", "קבוצת הודעות בשיחה אחת בין משתמש לעוזר AI.")
story.append(col_table([
    ["id",         "INT",          "PK, Auto-increment", "מזהה ייחודי"],
    ["user_id",    "INT",          "FK → User",          "בעל השיחה"],
    ["title",      "VARCHAR(200)", "NOT NULL",           "כותרת השיחה (אוטו / ידני)"],
    ["created_at", "TIMESTAMP",    "default NOW()",      "פתיחת השיחה"],
]))
story.append(Spacer(1, 6))

story += table_heading("AIChatMessage", "הודעה בודדת בתוך שיחת AI.")
story.append(col_table([
    ["id",         "INT",       "PK, Auto-increment", "מזהה ייחודי"],
    ["session_id", "INT",       "FK → AIChatSession", "השיחה האם"],
    ["role",       "ENUM",      "NOT NULL",           "user / assistant"],
    ["content",    "TEXT",      "NOT NULL",           "גוף ההודעה"],
    ["created_at", "TIMESTAMP", "default NOW()",      "זמן ההודעה"],
]))

# ── Relationships summary ──────────────────────────────────────────────────────
story += section("סיכום קשרים בין הטבלאות")
story.append(col_table([
    ["Category",       "Dish",           "1 : ∞", "Dish.category_id"],
    ["Dish",           "RecipeIngredient","1 : ∞", "RecipeIngredient.dish_id"],
    ["Ingredient",     "RecipeIngredient","1 : ∞", "RecipeIngredient.ingredient_id"],
    ["RestaurantTable","Order",           "1 : ∞", "Order.table_id"],
    ["User (מלצר)",    "Order",           "1 : ∞", "Order.waiter_id"],
    ["Order",          "OrderItem",       "1 : ∞", "OrderItem.order_id"],
    ["Dish",           "OrderItem",       "1 : ∞", "OrderItem.dish_id"],
    ["User (טבח)",     "OrderItem",       "1 : ∞ (opt)", "OrderItem.cook_id"],
    ["Ingredient",     "StockMovement",   "1 : ∞", "StockMovement.ingredient_id"],
    ["User",           "StockMovement",   "1 : ∞", "StockMovement.performed_by"],
    ["User",           "AIRecipeSuggestion","1 : ∞","AIRecipeSuggestion.requested_by"],
    ["User",           "AIChatSession",   "1 : ∞", "AIChatSession.user_id"],
    ["AIChatSession",  "AIChatMessage",   "1 : ∞", "AIChatMessage.session_id"],
], ["מ-טבלה", "אל-טבלה", "קשר", "דרך עמודה"]))

story.append(Spacer(1, 16))
story.append(p("© 2025 — אופק רותם ורון זרצקי | פרויקט גמר OOP", s_note))

# ── Build ─────────────────────────────────────────────────────────────────────
doc.build(story)
print(f"PDF created: {OUTPUT}")
