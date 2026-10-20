# Renders every figures/*.svg to a 2x PNG with headless Chrome (no network access needed).
# Run from the repository root:  powershell -File docs\project-report\figures\src\render_figures.ps1
# Chrome writes harmless diagnostics to stderr; do not treat them as failures.
$ErrorActionPreference = 'Continue'
$chrome = 'C:\Program Files\Google\Chrome\Application\chrome.exe'
$figures = Resolve-Path (Join-Path $PSScriptRoot '..')
$profileDir = Join-Path $env:TEMP 'ai-career-report-chrome'
Get-ChildItem $figures -Filter *.svg | ForEach-Object {
    $svg = $_.FullName
    $png = [IO.Path]::ChangeExtension($svg, '.png')
    $xml = [xml](Get-Content $svg -Raw -Encoding UTF8)
    $w = [int]$xml.svg.width; $h = [int]$xml.svg.height
    $uri = ([Uri]$svg).AbsoluteUri
    & $chrome --headless=new --disable-gpu --no-first-run --user-data-dir="$profileDir" `
        --hide-scrollbars --force-device-scale-factor=2 --window-size="$w,$h" `
        --default-background-color=FFFFFFFF --screenshot="$png" $uri 2>$null | Out-Null
    Write-Output "rendered $($_.Name) -> $([IO.Path]::GetFileName($png)) ($w x $h @2x)"
}
