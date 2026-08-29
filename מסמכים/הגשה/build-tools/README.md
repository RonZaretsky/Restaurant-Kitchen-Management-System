# פייפליין ההפקה

הפקת שני מסמכי ההגשה (DOCX + PDF) מקבצי הפרקים, כולל רינדור דיאגרמות Mermaid ויישור
RTL תקין.

## הפעלה

```powershell
# שני המסמכים, כולל רינדור מחדש של כל הדיאגרמות
powershell -File "מסמכים\הגשה\build\build-docs.ps1"

# מסמך אחד בלבד
powershell -File "מסמכים\הגשה\build\build-docs.ps1" -Document analysis
powershell -File "מסמכים\הגשה\build\build-docs.ps1" -Document design

# בלי לרנדר דיאגרמות מחדש (מהיר, כשרק הטקסט השתנה)
powershell -File "מסמכים\הגשה\build\build-docs.ps1" -SkipDiagrams

# DOCX בלבד, בלי לפתוח את Word
powershell -File "מסמכים\הגשה\build\build-docs.ps1" -SkipPdf
```

הפלט נכתב ל-`מסמכים/הגשה/output/`.

## מה צריך להיות מותקן

| כלי | לְמה | התקנה |
|---|---|---|
| pandoc | Markdown <- DOCX | `winget install --id JohnMacFarlane.Pandoc` |
| mermaid-cli | דיאגרמות <- PNG | `npm install -g @mermaid-js/mermaid-cli` |
| Python 3 | תיקון ה-RTL בקובץ ה-DOCX | קיים במחשב |
| Microsoft Word | DOCX <- PDF | קיים במחשב |
| poppler *(רשות)* | הצצה בעמודי ה-PDF כתמונות | `winget install --id oschwartz10612.Poppler` |

`mermaid-cli` מוריד Chromium משלו בהתקנה. אם npm חוסם את שלב ה-postinstall, מריצים ידנית:

```powershell
cd (Join-Path (npm root -g) "@mermaid-js\mermaid-cli\node_modules\puppeteer")
node "lib\puppeteer\node\cli.js" install chrome
```

## הקבצים

| קובץ | תפקיד |
|---|---|
| `build-docs.ps1` | הפייפליין המלא: איחוד פרקים <- pandoc <- RTL <- Word |
| `render-diagrams.ps1` | מרנדר כל `diagrams/*.md` ל-`diagrams/rendered/<שם>.png` |
| `apply-rtl.py` | מזריק לקובץ ה-DOCX את מאפייני ה-RTL של OOXML |

## איך משבצים דיאגרמה בתוך פרק

הדיאגרמות יושבות בקבצים נפרדים תחת `diagrams/`, קובץ אחד לכל דיאגרמה. בפרק מוסיפים
שורת סימון:

```markdown
<!-- diagram: usecase-waiter -->
```

בזמן ההפקה השורה הזו מוחלפת ב:

1. תמונת ה-PNG המרונדרת, בגודל שמתאים לרוחב העמוד;
2. **כל הטקסט שמופיע בקובץ הדיאגרמה אחרי בלוק ה-Mermaid** (כלומר "הסבר הפעולות"),
   כשכותרותיו יורדות ברמה אחת כדי להשתלב תחת הפרק.

כך אין שכפול: הסבר הדיאגרמה נכתב פעם אחת, בקובץ הדיאגרמה עצמו.

## למה ה-RTL נעשה ב-Python ולא ב-Word

הדרך המתבקשת הייתה לפתוח את המסמך ב-Word דרך COM ולהגדיר `ReadingOrder` לכל פסקה.
זה **לא עובד**: Word לא שומר את המאפיין בקובץ (נבדק - הוא שומר רק יישור לימין), והוא
לא הופך את סדר העמודות בטבלה בכלל. התוצאה נראית נכונה כל עוד הטקסט עברית טהורה,
ומתקלקלת ברגע שיש עברית ואנגלית באותה שורה - כלומר בכל מסמך עיצוב הפתרון.

לכן `apply-rtl.py` כותב ישירות ל-OOXML:

- `styles.xml` - `<w:bidi/>` ויישור לימין בברירת המחדל של הפסקאות, שכל הסגנונות יורשים;
- `styles.xml` - סגנון `SourceCode` מחזיר את עצמו ל-LTR, כדי שבלוקי קוד באנגלית ייקראו נכון;
- `document.xml` - `<w:bidiVisual/>` לכל טבלה, מה שהופך את סדר העמודות כך שהעמודה
  הראשונה יושבת מימין.

סדר האלמנטים בתוך `<w:pPr>` ו-`<w:tblPr>` נקבע בסכמה של OOXML, ו-Word פשוט מסרב לפתוח
קובץ שהסדר בו שגוי. לכן הקוד מזריק בנקודות מפורשות ולא מוסיף בסוף.

## יישור RTL: מה נכשל לפני שזה עבד

השלב שהכי קל לטעות בו. `<w:jc w:val="right"/>` נראה כמו הדבר הנכון לעשות, והוא **הפוך**:
ב-OOXML הערכים `left` ו-`right` פירושם `start` ו-`end`, כך שתחת `<w:bidi/>` הערך
`right` מיישר לשוליים ה**שמאליים**. התוצאה מטעה, כי הפיסוק והניקוד נראים נכון והטקסט
עצמו נדבק לצד הלא נכון. הפתרון: **לא לכתוב `w:jc` בכלל.** בלי `jc` הפסקה נופלת ל-`start`,
שתחת `bidi` הוא הצד הימני. `SourceCode` הוא היוצא מן הכלל, שם כן כתוב `jc="left"` יחד עם
`bidi="0"`, כלומר LTR אמיתי.

## מלכודות שכבר נפלנו בהן

- **קובץ `.ps1` עם עברית חייב BOM.** Windows PowerShell 5.1 קורא סקריפט בלי BOM
  כ-ANSI, וכל מחרוזת עברית בקובץ הופכת לג'יבריש ולשגיאת פרסור.
- **`Out-File -Encoding utf8` מוסיף BOM.** קובץ ה-JSON של puppeteer נכשל בגללו.
  משתמשים ב-`[System.IO.File]::WriteAllText` עם `UTF8Encoding($false)`.
- **`2>&1` על תוכנית חיצונית ב-PowerShell 5.1** עוטף כל שורת stderr ב-ErrorRecord
  ומפיל את הסקריפט גם כשהתוכנית הסתיימה בהצלחה.
- **`\newpage` נעלם בשקט** בהמרה ל-DOCX. מעברי עמוד נכתבים כ-OOXML גולמי
  (` ```{=openxml} `), ולכן ההמרה רצה עם `--from=markdown+raw_attribute`.
- **`Write-Output` בתוך פונקציה ב-PowerShell נכנס לערך ההחזרה שלה.** להדפסת התקדמות
  מתוך פונקציה משתמשים ב-`Write-Host`.
- **`ReadingOrder` ב-Word COM מקבל 0 או 1 בלבד**, לא 2 כפי שחלק מהמקורות מציינים.
- **הסקריפט סוגר את Word בסיום.** לכן `Assert-WordClosed` עוצר מראש אם Word כבר פתוח,
  ומבקש מכם לסגור אותו ידנית. **אין לעקוף את זה ב-`Stop-Process`:** אם פתוחים אצלכם
  מסמכים אחרים, הם ייסגרו יחד איתו. מי שרק צריך DOCX יריץ עם `-SkipPdf` ולא יגע ב-Word.

## מה לא נכנס ל-git

הפלט וכל הקבצים הנגזרים אינם נשמרים ב-git (ראו `.gitignore` בתיקיית `הגשה/`), מפני
שהם משוחזרים לגמרי מהמקור בפקודה אחת ורק היו מייצרים רעש בכל commit. **לפני ההגשה
עצמה** מוסיפים את הקבצים הסופיים במפורש:

```powershell
git add -f "מסמכים/הגשה/output/*.pdf" "מסמכים/הגשה/output/*.docx"
```
