<#
    Builds the two submission documents from their chapter files.

    Pipeline, per document:
        chapter *.md (in filename order)
          -> one merged .md, with every <!-- diagram: name --> marker expanded
             into the rendered PNG plus that diagram file's own explanation text
          -> pandoc  -> .docx
          -> apply-rtl.py -> the same .docx, patched to right-to-left
          -> Word    -> .pdf

    Requirements: pandoc, mermaid-cli (mmdc), python, and Microsoft Word.

    Usage:
        pwsh -File מסמכים/הגשה/build-tools/build-docs.ps1              # both documents
        pwsh -File .../build-docs.ps1 -Document analysis         # part A only
        pwsh -File .../build-docs.ps1 -Document design           # part B only
        pwsh -File .../build-docs.ps1 -SkipDiagrams              # reuse existing PNGs
        pwsh -File .../build-docs.ps1 -SkipPdf                   # DOCX only, no Word
#>

[CmdletBinding()]
param(
    [ValidateSet("all", "analysis", "design")]
    [string]$Document = "all",
    [switch]$SkipDiagrams,
    [switch]$SkipPdf
)

$ErrorActionPreference = "Stop"

$buildDir      = Split-Path -Parent $MyInvocation.MyCommand.Path
$submissionDir = Split-Path -Parent $buildDir
$diagramsDir   = Join-Path $submissionDir "diagrams"
$renderedDir   = Join-Path $diagramsDir "rendered"
$outputDir     = Join-Path $submissionDir "output"

New-Item -ItemType Directory -Force -Path $outputDir | Out-Null

$utf8NoBom = New-Object System.Text.UTF8Encoding($false)

# Page geometry the images are fitted into, in centimetres. A4 with 2.5cm
# margins leaves about 16cm of width and 24cm of height.
$maxImageWidthCm  = 15.0
$maxImageHeightCm = 20.0

# Screenshots are landscape and all get the same width, so the guide reads as a
# consistent column of images rather than a set of differently-sized ones.
$screenshotWidthCm = 14.0

# pandoc's installer puts it on the PATH, but a shell started before the install
# will not have picked that up yet, so fall back to the known install locations.
$pandoc = (Get-Command pandoc -ErrorAction SilentlyContinue).Source
if (-not $pandoc) {
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA "Pandoc\pandoc.exe"),
        "C:\Program Files\Pandoc\pandoc.exe"
    )
    $pandoc = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
}
if (-not $pandoc) {
    throw "pandoc not found. Install it with: winget install --id JohnMacFarlane.Pandoc"
}

function Assert-WordClosed {
    <#
        Refuses to continue while Word is already open.

        This script drives Word over COM and quits it when it is done. If Word
        is already running with the user's own documents, that quit takes those
        documents down with it, so an already-running Word is a hard stop here,
        never something to close automatically.
    #>
    if (-not (Get-Process WINWORD -ErrorAction SilentlyContinue)) {
        return
    }

    throw @"
Word is currently open, and this script would close it along with whatever you
have open in it. Nothing has been closed.

Please save and close Word yourself, then run this again. To build the DOCX now
and leave the PDF for later, re-run with -SkipPdf.
"@
}

# Checked up front, before any work: finding out that Word is in the way after
# the diagrams have been rendered and the DOCX built wastes the whole run.
if (-not $SkipPdf) {
    Assert-WordClosed
}

# The title page. Shared by both documents, since only the subtitle differs.
# Ron's identity number is still a placeholder, and is deliberately written in
# a form nobody could mistake for a real one.
$course        = "סדנה בתכנות מונחה עצמים (20586)"
$supervisor    = "מנחה: דני כלפון"
$submissionDay = "8 בספטמבר 2026"
$authors       = @(
    "אופק רותם, ת.ז. 204365092",
    "רון זרצקי, ת.ז. להשלמה"
)

$documents = @(
    [pscustomobject]@{
        Key       = "analysis"
        SourceDir = Join-Path $submissionDir "אפיון-וניתוח"
        BaseName  = "מסמך-אפיון-וניתוח"
        Title     = "Restaurant Kitchen Management System"
        Subtitle  = "מסמך אפיון וניתוח"
    },
    [pscustomobject]@{
        Key       = "design"
        SourceDir = Join-Path $submissionDir "עיצוב-פתרון"
        BaseName  = "מסמך-עיצוב-פתרון"
        Title     = "Restaurant Kitchen Management System"
        Subtitle  = "מסמך עיצוב הפתרון"
    }
)

if ($Document -ne "all") {
    $documents = $documents | Where-Object { $_.Key -eq $Document }
}

# ---------------------------------------------------------------------------
# Step 1: diagrams
# ---------------------------------------------------------------------------

if (-not $SkipDiagrams) {
    Write-Output "=== Rendering diagrams ==="
    & (Join-Path $buildDir "render-diagrams.ps1")
    Write-Output ""
}

# Stands in for any screenshot a chapter refers to but nobody has captured yet,
# so a half-illustrated guide still builds. Never overwrites a real capture.
Write-Output "=== Screenshots ==="
& (Join-Path $buildDir "make-screenshot-placeholders.ps1")
Write-Output ""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

function Get-ImageWidthCm {
    <#
        Returns the width in centimetres at which an image fits inside the page
        box, preserving its aspect ratio.
    #>
    param([string]$Path)

    Add-Type -AssemblyName System.Drawing
    $image = [System.Drawing.Image]::FromFile($Path)
    try {
        $aspect = $image.Height / $image.Width
    } finally {
        $image.Dispose()
    }

    $widthCm = $maxImageWidthCm
    if (($widthCm * $aspect) -gt $maxImageHeightCm) {
        $widthCm = $maxImageHeightCm / $aspect
    }
    return [math]::Round($widthCm, 2)
}

function Expand-DiagramMarker {
    <#
        Builds the Markdown that replaces a <!-- diagram: name --> marker: the
        rendered PNG, followed by the explanation text from the diagram's own
        source file (everything after its mermaid block), with that text's
        headings pushed one level down so they nest under the chapter section.
    #>
    param([string]$Name)

    $pngPath = Join-Path $renderedDir "$Name.png"
    $srcPath = Join-Path $diagramsDir "$Name.md"

    if (-not (Test-Path $pngPath)) {
        throw "Diagram '$Name' has no rendered PNG. Run render-diagrams.ps1 first."
    }
    if (-not (Test-Path $srcPath)) {
        throw "Diagram marker references '$Name', but $srcPath does not exist."
    }

    $widthCm = Get-ImageWidthCm -Path $pngPath
    # Forward slashes so pandoc resolves the path the same way on any shell.
    $imageRef = "![](" + ($pngPath -replace '\\', '/') + "){ width=" + $widthCm + "cm }"

    $srcText = Get-Content -Path $srcPath -Raw -Encoding utf8
    $afterFence = [regex]::Match($srcText, '(?s)```mermaid.*?```\r?\n(.*)$')
    $explanation = if ($afterFence.Success) { $afterFence.Groups[1].Value.Trim() } else { "" }

    # "## הסבר הפעולות" in a standalone diagram file should read as a
    # sub-sub-section once inlined into a chapter.
    $explanation = [regex]::Replace($explanation, '(?m)^(#{1,4})\s', '$1# ')

    return "$imageRef`r`n`r`n$explanation`r`n"
}

function Merge-Chapters {
    <#
        Concatenates a document's chapter files in filename order into one
        Markdown file, expanding every diagram marker on the way.
    #>
    param([pscustomobject]$Doc, [string]$MergedPath)

    $chapters = Get-ChildItem -Path $Doc.SourceDir -Filter "*.md" -File -ErrorAction SilentlyContinue |
        Sort-Object Name

    if (-not $chapters -or $chapters.Count -eq 0) {
        return 0
    }

    $sb = New-Object System.Text.StringBuilder

    # Pandoc reads this block as document metadata, not as body text, and the
    # docx writer renders it as the title page ahead of the table of contents.
    # The course and the supervisor ride in the author list rather than in
    # fields of their own: those are the only repeatable title-page lines the
    # writer offers, and on the page itself they read exactly as intended.
    [void]$sb.AppendLine('---')
    [void]$sb.AppendLine('title: "' + $Doc.Title + '"')
    [void]$sb.AppendLine('subtitle: "' + $Doc.Subtitle + '"')
    [void]$sb.AppendLine('author:')
    foreach ($author in $authors) {
        [void]$sb.AppendLine('  - "' + $author + '"')
    }
    [void]$sb.AppendLine('  - "' + $course + '"')
    [void]$sb.AppendLine('  - "' + $supervisor + '"')
    [void]$sb.AppendLine('date: "' + $submissionDay + '"')
    [void]$sb.AppendLine('lang: he')
    [void]$sb.AppendLine('dir: rtl')
    [void]$sb.AppendLine('toc-title: "תוכן עניינים"')
    [void]$sb.AppendLine('---')
    [void]$sb.AppendLine('')

    foreach ($chapter in $chapters) {
        # Write-Host, not Write-Output: anything this function writes to the
        # output stream is captured into its return value alongside the count.
        Write-Host ("  + " + $chapter.Name)
        $text = Get-Content -Path $chapter.FullName -Raw -Encoding utf8

        $text = [regex]::Replace($text, '<!--\s*diagram:\s*([A-Za-z0-9\-_]+)\s*-->', {
            param($m)
            Expand-DiagramMarker -Name $m.Groups[1].Value
        })

        # Screenshots are written as plain Markdown images so the chapters stay
        # readable, but at their natural pixel size they would run off the page.
        # One rule here beats repeating a width attribute on every one of them.
        $text = [regex]::Replace(
            $text,
            '(!\[[^\]]*\]\(screenshots/[A-Za-z0-9\-_]+\.png\))(?!\{)',
            "`$1{ width=$screenshotWidthCm" + "cm }"
        )

        [void]$sb.AppendLine($text.TrimEnd())
        [void]$sb.AppendLine('')
        # Each chapter starts on its own page. This has to be raw OOXML: the
        # docx writer silently discards a raw LaTeX newpage command, leaving
        # neither a page break nor an error.
        [void]$sb.AppendLine('```{=openxml}')
        [void]$sb.AppendLine('<w:p><w:r><w:br w:type="page"/></w:r></w:p>')
        [void]$sb.AppendLine('```')
        [void]$sb.AppendLine('')
    }

    [System.IO.File]::WriteAllText($MergedPath, $sb.ToString(), $utf8NoBom)
    return $chapters.Count
}

function Export-Pdf {
    <#
        Opens the (already right-to-left) DOCX in Word purely to export a PDF.
        The RTL work itself is done by apply-rtl.py against the OOXML, because
        Word's COM ReadingOrder does not persist and never flips a table's own
        column order.

        Call Assert-WordClosed first: this function quits Word on the way out.
    #>
    param([string]$DocxPath, [string]$PdfPath)

    $wdExportFormatPDF = 17

    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $word.DisplayAlerts = 0

    try {
        $doc = $word.Documents.Open($DocxPath)
        # Word numbers the table of contents from the layout Word itself
        # computes, so it has to be refreshed before the export or every page
        # number stays at pandoc's placeholder.
        foreach ($toc in $doc.TablesOfContents) { $toc.Update() | Out-Null }
        $doc.Save()
        $doc.ExportAsFixedFormat($PdfPath, $wdExportFormatPDF)
        $doc.Close($false)
    } finally {
        $word.Quit()
        [System.Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null
    }
}

# ---------------------------------------------------------------------------
# Step 2: build each document
# ---------------------------------------------------------------------------

$built = @()

foreach ($doc in $documents) {
    Write-Output ("=== " + $doc.BaseName + " ===")

    if (-not (Test-Path $doc.SourceDir)) {
        Write-Output "  (no source folder yet, skipping)"
        Write-Output ""
        continue
    }

    $mergedPath = Join-Path $outputDir ("_merged-" + $doc.BaseName + ".md")
    $docxPath   = Join-Path $outputDir ($doc.BaseName + ".docx")
    $pdfPath    = Join-Path $outputDir ($doc.BaseName + ".pdf")

    $count = Merge-Chapters -Doc $doc -MergedPath $mergedPath
    if ($count -eq 0) {
        Write-Output "  (no chapters written yet, skipping)"
        Write-Output ""
        continue
    }

    & $pandoc $mergedPath `
        --from=markdown+raw_attribute `
        --to=docx `
        --toc `
        --toc-depth=2 `
        --resource-path=$submissionDir `
        --output=$docxPath | Out-Null

    if (-not (Test-Path $docxPath)) {
        throw "pandoc produced no output for $($doc.BaseName)"
    }

    & python (Join-Path $buildDir "apply-rtl.py") $docxPath | Out-Null
    Write-Output ("  DOCX -> " + $docxPath)

    if (-not $SkipPdf) {
        Export-Pdf -DocxPath $docxPath -PdfPath $pdfPath
        Write-Output ("  PDF  -> " + $pdfPath)
    }

    $built += $doc.BaseName
    Write-Output ""
}

if ($built.Count -eq 0) {
    Write-Output "Nothing to build."
} else {
    Write-Output ("Built: " + ($built -join ", "))
}
