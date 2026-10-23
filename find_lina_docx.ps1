Add-Type -AssemblyName System.IO.Compression.FileSystem
$dirs = @(
    'C:\Users\eryma\Desktop',
    'C:\Users\eryma\Documents',
    'C:\Users\eryma\Downloads',
    'C:\Users\eryma\OneDrive',
    'C:\Users\eryma\CascadeProjects'
)
foreach ($d in $dirs) {
    if (-not (Test-Path $d)) { continue }
    Get-ChildItem $d -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Extension -eq '.docx' -and $_.FullName -notmatch '~\$' } |
        ForEach-Object {
            try {
                $zip = [System.IO.Compression.ZipFile]::OpenRead($_.FullName)
                $entry = $zip.Entries | Where-Object { $_.FullName -eq 'word/document.xml' } | Select-Object -First 1
                if ($entry) {
                    $sr = New-Object System.IO.StreamReader($entry.Open())
                    $xml = $sr.ReadToEnd(); $sr.Close()
                    $text = $xml -replace '<[^>]+>', ' '
                    if ($text -match '\bLina\b') {
                        $i = $text.IndexOf('Lina')
                        $ctx = $text.Substring([Math]::Max(0, $i - 80), [Math]::Min(200, $text.Length - [Math]::Max(0, $i - 80)))
                        $ctx = ($ctx -replace '\s+', ' ').Trim()
                        $count = ([regex]::Matches($text, '\bLina\b')).Count
                        Write-Output ("HIT x" + $count + " | " + $_.FullName)
                        Write-Output ("   ctx: ..." + $ctx + "...")
                    }
                }
                $zip.Dispose()
            } catch { }
        }
}
