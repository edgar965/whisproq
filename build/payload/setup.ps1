# Whisproq - Setup (laeuft aus der Setup-EXE heraus)
$ErrorActionPreference = "Stop"
$dst = Join-Path $env:LOCALAPPDATA "Whisproq"

Write-Host ""
Write-Host "=== Whisproq - Setup ===" -ForegroundColor Cyan
Write-Host "Installiere nach: $dst"

# evtl. laufende Instanzen beenden (EXE- und Python-Variante)
Get-Process -Name Whisproq -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like "*whisproq*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Milliseconds 800

# Programm entpacken
New-Item -ItemType Directory -Force -Path $dst | Out-Null
Expand-Archive -Path (Join-Path $PSScriptRoot "Whisproq.zip") -DestinationPath $dst -Force
Write-Host "Programm entpackt." -ForegroundColor Green

# GROQ_API_KEY (kostenlos)
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
    Write-Host "  Kostenlos-Kontingent: ca. 2 Stunden Diktat-Audio pro Tag."
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

# Autostart + sofort starten
$exe = Join-Path $dst "Whisproq.exe"
Set-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -Name "Whisproq" -Value ('"' + $exe + '"')
Start-Process -FilePath $exe
Write-Host ""
Write-Host "=== Fertig! ===" -ForegroundColor Cyan
Write-Host "F10 HALTEN -> sprechen -> loslassen. Satzzeichen mitdiktieren:"
Write-Host "  'Komma' , 'Punkt' . 'Fragezeichen' ? 'Ausrufezeichen' ! 'neue Zeile'"
Write-Host "Log: $dst\whisproq.log"
Start-Sleep -Seconds 6
