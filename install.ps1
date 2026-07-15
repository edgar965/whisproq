# =====================================================================
# Whisproq - Installer fuer Windows (venv-Variante)
# Richtet ein: Python-venv + Abhaengigkeiten + GROQ_API_KEY + Autostart.
# Aufruf: install.bat doppelklicken (oder diese Datei mit PowerShell).
# Idempotent - kann gefahrlos erneut laufen (Update/Reparatur).
# =====================================================================
$ErrorActionPreference = "Stop"
$HERE = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host ""
Write-Host "=== Whisproq - Installation ===" -ForegroundColor Cyan
Write-Host "Ordner: $HERE"
Write-Host ""

# --- 0) Alt-/Parallel-Varianten aufraeumen (nur EINE Installation darf
#         leben - sonst blockieren sich die Instanzen an Mutex/Mikrofon) ---
Get-Process -Name Whisproq, DiktatF10 -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Get-CimInstance Win32_Process -Filter "Name like 'pythonw%'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like "*whisproq*" -or $_.CommandLine -like "*diktat_f10*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Remove-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -Name "DiktatF10" -ErrorAction SilentlyContinue
$exeDir = Join-Path $env:LOCALAPPDATA "Whisproq"
if (Test-Path (Join-Path $exeDir "Whisproq.exe")) {
    Write-Host "Vorhandene EXE-Installation wird entfernt (Einstellungen bleiben) ..." -ForegroundColor Yellow
    Remove-Item -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\Whisproq" -Recurse -Force -ErrorAction SilentlyContinue
    Get-ChildItem $exeDir -Exclude config.json | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
}

# --- 1) Python 3 finden (py-Launcher oder python), sonst via winget holen ---
function Find-Python {
    foreach ($cand in @(@("py", "-3"), @("python"))) {
        try {
            $v = & $cand[0] $cand[1..($cand.Length)] --version 2>$null
            if ($LASTEXITCODE -eq 0 -and "$v" -match "Python 3") { return $cand }
        } catch {}
    }
    return $null
}

$py = Find-Python
if (-not $py) {
    Write-Host "Python 3 nicht gefunden - installiere via winget ..." -ForegroundColor Yellow
    winget install --id Python.Python.3.12 -e --accept-package-agreements --accept-source-agreements
    # PATH der frischen Installation nachladen
    $env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')
    $py = Find-Python
    if (-not $py) { throw "Python-Installation fehlgeschlagen - bitte Python 3 manuell installieren und Installer erneut starten." }
}
Write-Host ("Python gefunden: " + ($py -join " ")) -ForegroundColor Green

# --- 2) venv anlegen + Abhaengigkeiten installieren ---
$venvPy = Join-Path $HERE "venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    Write-Host "Lege venv an ..."
    & $py[0] $py[1..($py.Length)] -m venv (Join-Path $HERE "venv")
}
Write-Host "Installiere Abhaengigkeiten (keyboard, sounddevice) ..."
& $venvPy -m pip install --quiet --upgrade pip
& $venvPy -m pip install --quiet -r (Join-Path $HERE "requirements.txt")
Write-Host "Abhaengigkeiten ok." -ForegroundColor Green

# --- 3) GROQ_API_KEY (kostenlos) ---
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

# --- 4) Autostart (auf Wunsch) + sofort starten ---
$pyw = Join-Path $HERE "venv\Scripts\pythonw.exe"
$app = Join-Path $HERE "whisproq.py"
$cmd = '"' + $pyw + '" "' + $app + '"'
$auto = Read-Host "Whisproq beim Windows-Start automatisch starten? (j/n)"
if ($auto -match "^[jJyY]") {
    Set-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -Name "Whisproq" -Value $cmd
    Write-Host "Autostart eingetragen (HKCU\...\Run\Whisproq)." -ForegroundColor Green
} else {
    Remove-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -Name "Whisproq" -ErrorAction SilentlyContinue
    Write-Host "Kein Autostart - manuell starten: install-Ordner\venv\Scripts\pythonw.exe whisproq.py"
}

# evtl. laufende Instanz beenden, dann frisch starten
Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like "*whisproq.py*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Milliseconds 800
Start-Process -FilePath $pyw -ArgumentList "`"$app`"" -WorkingDirectory $HERE

Write-Host ""
Write-Host "=== Fertig! ===" -ForegroundColor Cyan
Write-Host "Bedienung: in ein Textfeld klicken, F10 GEDRUECKT HALTEN, sprechen,"
Write-Host "loslassen -> Text erscheint. Satzzeichen mitdiktieren:"
Write-Host "  'Komma' -> ,   'Punkt' -> .   'Fragezeichen' -> ?   'Ausrufezeichen' -> !"
Write-Host "  'neue Zeile' -> Zeilenumbruch"
Write-Host "Log bei Problemen: $HERE\whisproq.log"
