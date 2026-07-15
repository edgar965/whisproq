# Whisproq - Setup (laeuft aus der Setup-EXE heraus).
# WICHTIG: wird via `cmd /c start /wait` in einer EIGENEN Konsole gestartet -
# IExpress selbst startet das Install-Programm sonst mit verstecktem Fenster
# (gemessen: MainWindowHandle=0) und die Read-Host-Abfragen haengen unsichtbar.
$ErrorActionPreference = "Stop"
try { $host.UI.RawUI.WindowTitle = "Whisproq Setup" } catch {}
$dst = Join-Path $env:LOCALAPPDATA "Whisproq"
$ver = "0.21"  # muss zu __version__ in whisproq.py passen

Write-Host ""
Write-Host "=== Whisproq $ver - Setup ===" -ForegroundColor Cyan
Write-Host "Installiere nach: $dst"

# Update-Erkennung: liegt schon eine Installation vor, werden Key- und
# Autostart-Entscheidungen NICHT erneut abgefragt, sondern uebernommen.
$update = Test-Path (Join-Path $dst "Whisproq.exe")
if ($update) { Write-Host "Vorhandene Installation gefunden - fuehre Update durch." -ForegroundColor Yellow }

# --- ALLE Diktat-Varianten beenden, damit nur EINE Installation bleibt ---
# (EXE-Variante, venv-Variante, Vorgaenger "DiktatF10" - laufen sonst
#  parallel und blockieren sich gegenseitig am Mikrofon/Mutex)
Get-Process -Name Whisproq, DiktatF10 -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Get-CimInstance Win32_Process -Filter "Name like 'pythonw%'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like "*whisproq*" -or $_.CommandLine -like "*diktat_f10*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
# Alt-Autostarts entfernen (der neue Eintrag "Whisproq" wird unten gesetzt)
Remove-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -Name "DiktatF10" -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 800

# --- Programm entpacken ---
# Das Zip enthaelt KEINE config.json (Defaults stehen im Code; die
# User-Config entsteht erst beim Speichern im Zahnrad) — ein Update kann
# vorhandene Einstellungen daher gar nicht ueberschreiben.
New-Item -ItemType Directory -Force -Path $dst | Out-Null
Expand-Archive -Path (Join-Path $PSScriptRoot "Whisproq.zip") -DestinationPath $dst -Force
if ($update) {
    Write-Host "Programm aktualisiert (Einstellungen bleiben unberuehrt)." -ForegroundColor Green
} else {
    Write-Host "Programm entpackt." -ForegroundColor Green
}

# --- GROQ_API_KEY (kostenlos) ---
$key = [Environment]::GetEnvironmentVariable("GROQ_API_KEY", "User")
if (-not $key) {
    Write-Host ""
    Write-Host "--- Groq-API-Key holen (kostenlos, 2 Minuten) ---" -ForegroundColor Yellow
    Write-Host "  1. Im Browser oeffnen:  https://console.groq.com/keys"
    Write-Host "  2. Kostenlos registrieren/anmelden (Google-Konto oder E-Mail,"
    Write-Host "     keine Kreditkarte noetig)"
    Write-Host "  3. Auf 'Create API Key' klicken, Namen vergeben (z.B. 'Whisproq'),"
    Write-Host "     'Submit' klicken"
    Write-Host "  4. Den angezeigten Key kopieren (beginnt mit 'gsk_...')"
    Write-Host "     ACHTUNG: er wird nur EINMAL angezeigt!"
    Write-Host "  5. Hier unten einfuegen (Rechtsklick ins Fenster = Einfuegen)"
    Write-Host ""
    Write-Host "  Kostenlos-Kontingent: bis zu 8 Stunden Diktat-Audio pro Tag."
    Write-Host ""
    $open = Read-Host "Soll ich https://console.groq.com/keys jetzt im Browser oeffnen? (j/n)"
    if ($open -match "^[jJyY]") { Start-Process "https://console.groq.com/keys" }
    $key = Read-Host "GROQ_API_KEY hier einfuegen"
    if ($key) {
        [Environment]::SetEnvironmentVariable("GROQ_API_KEY", $key.Trim(), "User")
        Write-Host "Key gespeichert (User-Umgebung dieses Rechners)." -ForegroundColor Green
    } else {
        Write-Host "Kein Key eingegeben - Whisproq startet erst, wenn er gesetzt ist:" -ForegroundColor Yellow
        Write-Host "  setx GROQ_API_KEY <dein_key>   (wirkt sofort, ohne Neustart)"
    }
} else {
    Write-Host "GROQ_API_KEY bereits gesetzt." -ForegroundColor Green
}

# --- Eintrag in "Installierte Apps" (deinstallierbar ueber Windows) ---
$exe = Join-Path $dst "Whisproq.exe"
$un = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\Whisproq"
New-Item -Path $un -Force | Out-Null
Set-ItemProperty -Path $un -Name "DisplayName" -Value "Whisproq"
Set-ItemProperty -Path $un -Name "DisplayVersion" -Value $ver
Set-ItemProperty -Path $un -Name "Publisher" -Value "edgar965"
Set-ItemProperty -Path $un -Name "InstallLocation" -Value $dst
Set-ItemProperty -Path $un -Name "DisplayIcon" -Value $exe
Set-ItemProperty -Path $un -Name "UninstallString" -Value ('powershell.exe -NoProfile -ExecutionPolicy Bypass -File "' + (Join-Path $dst "uninstall.ps1") + '"')
Set-ItemProperty -Path $un -Name "QuietUninstallString" -Value ('powershell.exe -NoProfile -ExecutionPolicy Bypass -File "' + (Join-Path $dst "uninstall.ps1") + '" -Quiet')
Set-ItemProperty -Path $un -Name "NoModify" -Value 1 -Type DWord
Set-ItemProperty -Path $un -Name "NoRepair" -Value 1 -Type DWord
$sizeKB = [int]((Get-ChildItem $dst -Recurse | Measure-Object Length -Sum).Sum / 1KB)
Set-ItemProperty -Path $un -Name "EstimatedSize" -Value $sizeKB -Type DWord
Write-Host "In 'Installierte Apps' registriert (deinstallierbar)." -ForegroundColor Green

# --- Autostart + sofort starten ---
# Update: bestehende Autostart-Entscheidung uebernehmen (Eintrag vorhanden ->
# bleibt, zeigt auf die neue EXE; nicht vorhanden -> bleibt weg, keine Frage).
$runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$hadAuto = $null -ne (Get-ItemProperty -Path $runKey -Name "Whisproq" -ErrorAction SilentlyContinue)
if ($update) {
    if ($hadAuto) {
        Set-ItemProperty -Path $runKey -Name "Whisproq" -Value ('"' + $exe + '"')
        Write-Host "Update: Autostart beibehalten." -ForegroundColor Green
    } else {
        Write-Host "Update: kein Autostart (wie bisher)."
    }
} else {
    Write-Host ""
    $auto = Read-Host "Whisproq beim Windows-Start automatisch starten? (j/n)"
    if ($auto -match "^[jJyY]") {
        Set-ItemProperty -Path $runKey -Name "Whisproq" -Value ('"' + $exe + '"')
        Write-Host "Autostart eingetragen." -ForegroundColor Green
    } else {
        Remove-ItemProperty -Path $runKey -Name "Whisproq" -ErrorAction SilentlyContinue
        Write-Host "Kein Autostart - manuell starten: $exe"
    }
}
Start-Process -FilePath $exe
Write-Host ""
Write-Host "=== Fertig! ===" -ForegroundColor Cyan
Write-Host "F10 HALTEN -> sprechen -> loslassen. Satzzeichen mitdiktieren:"
Write-Host "  'Komma' , 'Punkt' . 'Fragezeichen' ? 'Ausrufezeichen' ! 'neue Zeile'"
Write-Host "Deinstallieren: Windows-Einstellungen -> Apps -> Whisproq"
Write-Host "Log: $dst\whisproq.log"
Start-Sleep -Seconds 6
