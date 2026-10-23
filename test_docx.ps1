Add-Type -AssemblyName System.IO.Compression.FileSystem
$f = 'C:\Users\eryma\Desktop\La_storia_di_Anna_materiale_grezzo.docx'
$zip = [System.IO.Compression.ZipFile]::OpenRead($f)
$entry = $zip.Entries | Where-Object { $_.FullName -eq 'word/document.xml' } | Select-Object -First 1
$sr = New-Object System.IO.StreamReader($entry.Open())
$xml = $sr.ReadToEnd(); $sr.Close(); $zip.Dispose()
$text = $xml -replace '<[^>]+>', ' '
Write-Output ('LEN: ' + $text.Length)
Write-Output ($text.Substring(0, [Math]::Min(800, $text.Length)))
