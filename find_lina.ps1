$dirs = @(
    'C:\Users\eryma\OneDrive',
    'C:\Users\eryma\CascadeProjects',
    'C:\Users\eryma\Desktop',
    'C:\Users\eryma\Documents',
    'C:\Users\eryma\Downloads'
)
foreach ($d in $dirs) {
    if (Test-Path $d) {
        Get-ChildItem $d -Recurse -File -ErrorAction SilentlyContinue |
            Where-Object { $_.Extension -in '.txt','.md','.rtf' -and $_.Length -lt 5MB } |
            ForEach-Object {
                $hit = Select-String -Path $_.FullName -Pattern '\bLina\b' -ErrorAction SilentlyContinue | Select-Object -First 1
                if ($hit) { Write-Output ("FILE: " + $_.FullName + " | " + $_.LastWriteTime + " | riga: " + $hit.Line.Trim().Substring(0, [Math]::Min(120, $hit.Line.Trim().Length))) }
            }
    }
}
