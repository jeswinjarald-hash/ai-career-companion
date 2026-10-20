# Fills the Word fields of AI_Career_Companion_Project_Report.docx (table of contents,
# list of figures, list of tables, page numbers) and saves the document.
# Requires Microsoft Word on Windows. Run from the repository root:
#   powershell -ExecutionPolicy Bypass -File docs\project-report\tools\update_docx_fields.ps1
# A separate, hidden Word instance is used; it opens only the report and is quit only if
# it has no other documents open. (PDF export through Word was not used: in this
# environment Word's PDF export stalled, so build_pdf.py renders the PDF instead.)
$ErrorActionPreference = 'Stop'
$root = Resolve-Path (Join-Path $PSScriptRoot '..')
$docx = Join-Path $root 'AI_Career_Companion_Project_Report.docx'

$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
$doc = $null
try {
    $doc = $word.Documents.Open([string]$docx, $false, $false, $false)
    # Two passes: the first fills the lists, the second corrects page numbers that moved.
    for ($pass = 1; $pass -le 2; $pass++) {
        $doc.Fields.Update() | Out-Null
        foreach ($toc in $doc.TablesOfContents) { $toc.Update() }
        $doc.Repaginate()
    }
    $doc.Save()
    $pages = $doc.ComputeStatistics(2)  # 2 = wdStatisticPages
    Write-Output "updated fields in $docx ($pages pages as paginated by Word)"
}
finally {
    if ($doc) { $doc.Close($false) }
    if ($word.Documents.Count -eq 0) { $word.Quit() }
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null
}
