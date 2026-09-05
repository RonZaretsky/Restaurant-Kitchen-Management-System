<#
    Creates a labelled placeholder PNG for every screenshot a chapter refers to
    but that has not been captured yet.

    There is no list of screenshots to maintain: the chapters themselves are the
    source of truth. This scans every chapter for image references of the form

        ![caption text](screenshots/NAME.png)

    and, for each one with no file behind it, draws a placeholder carrying that
    caption and the file name. Replacing a placeholder is just dropping the real
    capture in at the same path and rebuilding, with no edit to the Markdown.

    An existing file is NEVER overwritten, so running this after some real
    screenshots have landed only fills the gaps.

    Usage:
        powershell -File מסמכים/הגשה/build-tools/make-screenshot-placeholders.ps1
        powershell -File .../make-screenshot-placeholders.ps1 -List   # report only
#>

[CmdletBinding()]
param([switch]$List)

$ErrorActionPreference = "Stop"

Add-Type -AssemblyName System.Drawing

$buildDir      = Split-Path -Parent $MyInvocation.MyCommand.Path
$submissionDir = Split-Path -Parent $buildDir
$shotsDir      = Join-Path $submissionDir "screenshots"

New-Item -ItemType Directory -Force -Path $shotsDir | Out-Null

$width  = 1200
$height = 750

# Collect every screenshots/*.png reference across both documents' chapters.
$chapterDirs = @(
    (Join-Path $submissionDir "אפיון-וניתוח"),
    (Join-Path $submissionDir "עיצוב-פתרון")
) | Where-Object { Test-Path $_ }

$wanted = [ordered]@{}
foreach ($dir in $chapterDirs) {
    foreach ($file in Get-ChildItem -Path $dir -Filter "*.md" -File) {
        $text = Get-Content -Path $file.FullName -Raw -Encoding utf8
        foreach ($m in [regex]::Matches($text, '!\[([^\]]*)\]\(screenshots/([A-Za-z0-9\-_]+\.png)\)')) {
            $name = $m.Groups[2].Value
            if (-not $wanted.Contains($name)) {
                $wanted[$name] = $m.Groups[1].Value
            }
        }
    }
}

if ($wanted.Count -eq 0) {
    Write-Output "No screenshot references found in any chapter."
    exit 0
}

$missing = @($wanted.Keys | Where-Object { -not (Test-Path (Join-Path $shotsDir $_)) })
$present = $wanted.Count - $missing.Count

Write-Output ("Referenced: {0}   captured: {1}   missing: {2}" -f $wanted.Count, $present, $missing.Count)

if ($List) {
    foreach ($name in $wanted.Keys) {
        $mark = if (Test-Path (Join-Path $shotsDir $name)) { "have" } else { "TODO" }
        Write-Output ("  [{0}] {1}  {2}" -f $mark, $name, $wanted[$name])
    }
    exit 0
}

function New-Placeholder {
    <#
        Draws one placeholder PNG: a light panel, a dashed border, the caption
        in Hebrew and the target file name underneath.
    #>
    param([string]$Path, [string]$Caption, [string]$Name)

    $bitmap   = New-Object System.Drawing.Bitmap($width, $height)
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)

    try {
        $graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
        $graphics.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::ClearTypeGridFit
        $graphics.Clear([System.Drawing.Color]::FromArgb(245, 245, 248))

        $pen = New-Object System.Drawing.Pen([System.Drawing.Color]::FromArgb(150, 150, 165), 4)
        $pen.DashStyle = [System.Drawing.Drawing2D.DashStyle]::Dash
        $graphics.DrawRectangle($pen, 20, 20, $width - 40, $height - 40)

        # Hebrew needs an explicit right-to-left layout, or the words render in
        # the wrong order regardless of the font.
        $rtl = New-Object System.Drawing.StringFormat
        $rtl.Alignment = [System.Drawing.StringAlignment]::Center
        $rtl.LineAlignment = [System.Drawing.StringAlignment]::Center
        $rtl.FormatFlags = [System.Drawing.StringFormatFlags]::DirectionRightToLeft

        $ltr = New-Object System.Drawing.StringFormat
        $ltr.Alignment = [System.Drawing.StringAlignment]::Center
        $ltr.LineAlignment = [System.Drawing.StringAlignment]::Center

        $titleFont   = New-Object System.Drawing.Font("Arial", 30, [System.Drawing.FontStyle]::Bold)
        $captionFont = New-Object System.Drawing.Font("Arial", 22)
        $nameFont    = New-Object System.Drawing.Font("Consolas", 18)

        $dark = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(70, 70, 90))
        $mid  = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(110, 110, 130))

        $graphics.DrawString("כאן ייכנס צילום מסך", $titleFont, $dark,
            (New-Object System.Drawing.RectangleF(60, 190, ($width - 120), 70)), $rtl)

        $graphics.DrawString($Caption, $captionFont, $mid,
            (New-Object System.Drawing.RectangleF(80, 290, ($width - 160), 200)), $rtl)

        $graphics.DrawString($Name, $nameFont, $mid,
            (New-Object System.Drawing.RectangleF(60, 520, ($width - 120), 50)), $ltr)

        $bitmap.Save($Path, [System.Drawing.Imaging.ImageFormat]::Png)
    } finally {
        $graphics.Dispose()
        $bitmap.Dispose()
    }
}

foreach ($name in $missing) {
    $target = Join-Path $shotsDir $name
    New-Placeholder -Path $target -Caption $wanted[$name] -Name $name
    Write-Output ("  placeholder -> " + $name)
}

Write-Output ""
Write-Output "Drop a real capture in at the same path to replace a placeholder. Nothing here is ever overwritten."
