$dirs = @(
    'C:\Users\eryma\AppData\Local\Packages\OpenAI.ChatGPT-Desktop_2p2nqsd0c76g0',
    'C:\Users\eryma\AppData\Roaming\ChatGPT',
    'C:\Users\eryma\AppData\Roaming\OpenAI'
)
foreach ($d in $dirs) {
    if (Test-Path $d) {
        Write-Output "=== $d ==="
        Get-ChildItem $d -Recurse -File -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -match 'convers|history|chat|db|sqlite|local|state|storage' -or $_.Extension -in '.db','.sqlite','.sqlite3','.json' } |
            Select-Object FullName, Length, LastWriteTime |
            Format-Table -AutoSize | Out-String -Width 250
    }
}
Write-Output '=== LocalState/LocalCache del package ==='
$pkg = 'C:\Users\eryma\AppData\Local\Packages\OpenAI.ChatGPT-Desktop_2p2nqsd0c76g0'
Get-ChildItem $pkg -Directory -Recurse -Depth 3 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName
