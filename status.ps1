<#
.SYNOPSIS
  Status di tutti i processi di acquisizione IMI Extractor con percentuali.
.USAGE
  .\status.ps1              # snapshot singolo
  .\status.ps1 -Watch       # refresh ogni 10s
  .\status.ps1 -Watch 5     # refresh ogni 5s
#>
param(
    [switch]$Watch,
    [int]$Interval = 10
)

$ErrorActionPreference = "SilentlyContinue"
$db = Join-Path $PSScriptRoot "imi_internati.db"

function Get-DbCount($query) {
    $result = python -c "from database import get_conn; c=get_conn(); print(c.execute('$query').fetchone()[0]); c.close()" 2>$null
    if ($result -match '^\d+$') { return [int64]$result } else { return -1 }
}

function Get-DbRows($query) {
    $raw = python -c "from database import get_conn; c=get_conn(); [print(f'{r[0]}|{r[1]}') for r in c.execute('$query').fetchall()]; c.close()" 2>$null
    $rows = @()
    foreach ($line in $raw) {
        $parts = $line -split '\|',2
        if ($parts.Count -eq 2) { $rows += [PSCustomObject]@{Name=$parts[0]; Value=$parts[1]} }
    }
    return $rows
}

function Show-Status {
    Clear-Host
    $now = Get-Date -Format "dd/MM/yyyy HH:mm:ss"
    Write-Host "`n  IMI EXTRACTOR - Status acquisizioni ($now)" -ForegroundColor Cyan
    Write-Host "  ====================================================" -ForegroundColor Cyan

    # Processi Python attivi - identifica per log file timestamps
    $procs = Get-Process python -ErrorAction SilentlyContinue | Select-Object Id, StartTime, CPU

    # Linker e' il processo con CPU accumulata alta (gira da ore)
    $linkerProc = $procs | Where-Object { $_.CPU -gt 500 } | Sort-Object StartTime | Select-Object -First 1

    # NARA: verifica log recente
    $naraLogFile = Join-Path $PSScriptRoot "nara_scrape.log"
    $naraLogTime = (Get-Item $naraLogFile -ErrorAction SilentlyContinue).LastWriteTime
    $naraProc = $null
    if ($naraLogTime -and ((Get-Date) - $naraLogTime).TotalMinutes -le 5) {
        $naraProc = $procs | Where-Object { $_.Id -ne $linkerProc.Id } | Sort-Object StartTime -Descending | Select-Object -First 1
    }

    # CWGC: verifica log recente (anche 10 min per buffering stdout)
    $cwgcLogFile = Join-Path $PSScriptRoot "cwgc_log.txt"
    $cwgcLogTime = (Get-Item $cwgcLogFile -ErrorAction SilentlyContinue).LastWriteTime
    $cwgcProc = $null
    if ($cwgcLogTime -and ((Get-Date) - $cwgcLogTime).TotalMinutes -le 10) {
        $cwgcProc = $procs | Where-Object { $_.Id -ne $linkerProc.Id -and $_.Id -ne $naraProc.Id } | Sort-Object StartTime -Descending | Select-Object -First 1
    }

    # Conteggi DB
    $nara       = Get-DbCount "SELECT COUNT(*) FROM documenti_nara_t315"
    $naraTarget = 1153
    $albo       = Get-DbCount "SELECT COUNT(*) FROM caduti_albooro"
    $ministero  = Get-DbCount "SELECT COUNT(*) FROM caduti_ministero"
    $sardi      = Get-DbCount "SELECT COUNT(*) FROM caduti_sardi"
    $bologna    = Get-DbCount "SELECT COUNT(*) FROM caduti_bologna"
    $cwgc       = Get-DbCount "SELECT COUNT(*) FROM caduti_cwgc"
    $cwgcTarget = 1763187
    $internati  = Get-DbCount "SELECT COUNT(*) FROM internati"
    $decorati   = Get-DbCount "SELECT COUNT(*) FROM decorati"
    $entita     = Get-DbCount "SELECT COUNT(*) FROM entita"
    $coll       = Get-DbCount "SELECT COUNT(*) FROM collegamenti"

    # Ultimo frame NARA
    $naraLast = python -c "from database import get_conn; c=get_conn(); r=c.execute('SELECT frame, elaborato_il FROM documenti_nara_t315 ORDER BY elaborato_il DESC LIMIT 1').fetchone(); print(f'{r[0]}|{r[1][:19]}') if r else print('-'); c.close()" 2>$null

    # CWGC per nazionalita
    $cwgcNats = Get-DbRows "SELECT nationality, COUNT(*) FROM caduti_cwgc GROUP BY nationality ORDER BY COUNT(*) DESC LIMIT 8"

    # Collegamenti per tabella
    $collTabs = Get-DbRows "SELECT tabella_origine, COUNT(*) FROM collegamenti GROUP BY tabella_origine ORDER BY COUNT(*) DESC"

    # Tabella principale
    Write-Host ""
    $datasets = @(
        @{Name="NARA T315 R1299 (OCR)";       Table="documenti_nara_t315"; Count=$nara;       Target=$naraTarget;  Proc=$naraProc},
        @{Name="Albo d'Oro";                   Table="caduti_albooro";      Count=$albo;       Target=342555;       Proc=$null},
        @{Name="Caduti Ministero Difesa";      Table="caduti_ministero";    Count=$ministero;  Target=162646;       Proc=$null},
        @{Name="Caduti Sardi";                 Table="caduti_sardi";        Count=$sardi;      Target=20435;        Proc=$null},
        @{Name="Caduti Bolognesi";             Table="caduti_bologna";      Count=$bologna;    Target=9656;         Proc=$null},
        @{Name="CWGC (tutte nazionalita)";     Table="caduti_cwgc";         Count=$cwgc;       Target=$cwgcTarget;  Proc=$cwgcProc},
        @{Name="Internati Militari Italiani";  Table="internati";           Count=$internati;  Target=20464;        Proc=$null},
        @{Name="Decorati al Valor Militare";   Table="decorati";            Count=$decorati;   Target=1286;         Proc=$null}
    )

    $fmt = "  {0,-32} {1,12:N0} / {2,12:N0}  {3,7}  {4}"
    Write-Host ($fmt -f "Dataset", "Record", "Target", "%", "Stato")
    Write-Host "  " + ("-"*80)

    foreach ($d in $datasets) {
        $pct = if ($d.Target -gt 0) { ($d.Count / $d.Target * 100) } else { 0 }
        $pctStr = "{0:N1}%" -f $pct

        if ($d.Count -ge $d.Target -and $d.Target -gt 0) {
            $status = "OK completo"
            $color = "Green"
        } elseif ($d.Proc -and $d.Count -lt $d.Target) {
            $status = "IN CORSO (pid $($d.Proc.Id))"
            $color = "Yellow"
        } elseif ($d.Count -gt 0 -and -not $d.Proc) {
            $status = "completo"
            $color = "Green"
        } else {
            $status = "fermo"
            $color = "Red"
        }

        $line = $fmt -f $d.Name, $d.Count, $d.Target, $pctStr, $status
        Write-Host $line -ForegroundColor $color
    }

    # Barra progresso NARA
    if ($nara -gt 0 -and $nara -lt $naraTarget) {
        $barLen = 30
        $filled = [math]::Floor($nara / $naraTarget * $barLen)
        $bar = ("#" * $filled) + ("." * ($barLen - $filled))
        Write-Host ""
        Write-Host "  NARA  [$bar] $nara/$naraTarget" -ForegroundColor Yellow
        if ($naraLast -and $naraLast -ne "-") {
            $parts = $naraLast -split '\|'
            Write-Host "        ultimo frame: $($parts[0]) @ $($parts[1])" -ForegroundColor DarkGray
        }
    }

    # Barra progresso CWGC
    if ($cwgc -gt 0 -and $cwgc -lt $cwgcTarget) {
        $barLen = 30
        $filled = [math]::Floor($cwgc / $cwgcTarget * $barLen)
        $bar = ("#" * $filled) + ("." * ($barLen - $filled))
        $pct = "{0:N2}%" -f ($cwgc / $cwgcTarget * 100)
        Write-Host ""
        Write-Host "  CWGC  [$bar] $cwgc / $cwgcTarget ($pct)" -ForegroundColor Yellow
        if ($cwgcNats.Count -gt 0) {
            $natStr = ($cwgcNats | ForEach-Object { "$($_.Name): $($_.Value)" }) -join " | "
            Write-Host "        $natStr" -ForegroundColor DarkGray
        }
    }

    # Linker
    Write-Host ""
    Write-Host "  LINKER" -ForegroundColor Cyan
    $linkerStatus = if ($linkerProc) { "IN CORSO (pid $($linkerProc.Id))" } else { "fermo" }
    $linkerColor  = if ($linkerProc) { "Yellow" } else { "Red" }
    Write-Host "    Entita:       $entita" -ForegroundColor White
    Write-Host "    Collegamenti: $coll  [$linkerStatus]" -ForegroundColor $linkerColor
    if ($collTabs) {
        foreach ($t in $collTabs) {
            Write-Host "      $($t.Name): $($t.Value)" -ForegroundColor DarkGray
        }
    }

    # Processi attivi
    Write-Host ""
    Write-Host "  PROCESSI PYTHON ATTIVI" -ForegroundColor Cyan
    if ($procs) {
        foreach ($p in $procs) {
            $age = ((Get-Date) - $p.StartTime).ToString("hh\:mm\:ss")
            Write-Host "    pid $($p.Id) | CPU $([math]::Round($p.CPU,1))s | attivo da $age" -ForegroundColor DarkGray
        }
    } else {
        Write-Host "    nessun processo Python attivo" -ForegroundColor Red
    }

    Write-Host ""
}

if ($Watch) {
    while ($true) {
        Show-Status
        Write-Host "  Refresh tra $Interval s... (Ctrl+C per uscire)" -ForegroundColor DarkGray
        Start-Sleep $Interval
    }
} else {
    Show-Status
}
