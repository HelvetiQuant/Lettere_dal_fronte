$dirs = @(
    'C:\Users\eryma\Desktop',
    'C:\Users\eryma\Documents',
    'C:\Users\eryma\Downloads',
    'C:\Users\eryma\OneDrive',
    'C:\Users\eryma\CascadeProjects'
)
foreach ($d in $dirs) {
    if (Test-Path $d) {
        Get-ChildItem $d -Recurse -File -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -match 'appunti|fedeli|pensieri|racconto|storia|memorie' } |
            Select-Object FullName, LastWriteTime, Length |
            Format-Table -AutoSize | Out-String -Width 250
    }
}
Write-Output '=== file di testo modificati a gennaio 2026 ==='
foreach ($d in $dirs) {
    if (Test-Path $d) {
        Get-ChildItem $d -Recurse -File -ErrorAction SilentlyContinue |
            Where-Object { $_.Extension -in '.txt','.md','.docx','.pdf','.rtf' -and $_.LastWriteTime -gt '2026-01-01' -and $_.LastWriteTime -lt '2026-02-01' } |
            Select-Object FullName, LastWriteTime |
            Format-Table -AutoSize | Out-String -Width 250
    }
}
