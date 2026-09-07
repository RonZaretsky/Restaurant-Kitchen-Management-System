<#
    Renders every Mermaid diagram under מסמכים/הגשה/diagrams/ to a PNG in
    diagrams/rendered/.

    Each diagram file is a Markdown file holding exactly one ```mermaid fenced
    block. This script extracts that block into a temporary .mmd file, hands it
    to mermaid-cli (mmdc), and writes <name>.png next to the others.

    Run from anywhere:
        pwsh -File מסמכים/הגשה/build-tools/render-diagrams.ps1
#>

$ErrorActionPreference = "Stop"

$buildDir     = Split-Path -Parent $MyInvocation.MyCommand.Path
$submissionDir = Split-Path -Parent $buildDir
$diagramsDir  = Join-Path $submissionDir "diagrams"
$renderedDir  = Join-Path $diagramsDir "rendered"
$tempDir      = Join-Path $env:TEMP "rkms-mermaid"

New-Item -ItemType Directory -Force -Path $renderedDir | Out-Null
New-Item -ItemType Directory -Force -Path $tempDir | Out-Null

# mermaid-cli renders through headless Chromium, which refuses to start under a
# sandboxed parent process without these flags.
# Written without a BOM: Windows PowerShell's `Out-File -Encoding utf8` emits one,
# and mmdc's JSON.parse chokes on it.
$puppeteerConfig = Join-Path $tempDir "puppeteer.json"
[System.IO.File]::WriteAllText(
    $puppeteerConfig,
    '{ "args": ["--no-sandbox", "--disable-gpu"] }',
    (New-Object System.Text.UTF8Encoding($false))
)

$sources = Get-ChildItem -Path $diagramsDir -Filter "*.md" -File | Sort-Object Name
if ($sources.Count -eq 0) {
    Write-Output "No diagram files found in $diagramsDir"
    exit 0
}

$failed = @()

foreach ($source in $sources) {
    $name = [System.IO.Path]::GetFileNameWithoutExtension($source.Name)
    $text = Get-Content -Path $source.FullName -Raw -Encoding utf8

    # Pull out the single ```mermaid ... ``` block.
    $match = [regex]::Match($text, '(?s)```mermaid\r?\n(.*?)```')
    if (-not $match.Success) {
        Write-Output "SKIP  $name  (no mermaid block)"
        continue
    }

    $mmdPath = Join-Path $tempDir "$name.mmd"
    $pngPath = Join-Path $renderedDir "$name.png"

    # -NoNewline plus an explicit UTF8 write keeps Hebrew labels intact; mmdc
    # reads the file as UTF-8 and a BOM would land inside the first node label.
    [System.IO.File]::WriteAllText($mmdPath, $match.Groups[1].Value, (New-Object System.Text.UTF8Encoding($false)))

    Write-Output "RENDER $name"
    # No 2>&1 here: Windows PowerShell 5.1 wraps a native command's stderr in an
    # ErrorRecord and trips $ErrorActionPreference = "Stop" even on a clean exit.
    & mmdc -i $mmdPath -o $pngPath -b white -w 1600 -s 2 -p $puppeteerConfig | Out-Null

    if (-not (Test-Path $pngPath)) {
        $failed += $name
    }
}

if ($failed.Count -gt 0) {
    Write-Output ""
    Write-Output "FAILED to render: $($failed -join ', ')"
    exit 1
}

Write-Output ""
Write-Output "All diagrams rendered to $renderedDir"
