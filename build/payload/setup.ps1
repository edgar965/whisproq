# Whisproq - Setup (laeuft aus der Setup-EXE heraus).
# WICHTIG: wird via `cmd /c start /wait` in einer EIGENEN Konsole gestartet -
# IExpress selbst startet das Install-Programm sonst mit verstecktem Fenster
# (gemessen: MainWindowHandle=0) und die Read-Host-Abfragen haengen unsichtbar.
$ErrorActionPreference = "Stop"
try { $host.UI.RawUI.WindowTitle = "Whisproq Setup" } catch {}
$dst = Join-Path $env:LOCALAPPDATA "Whisproq"
$ver = "0.28"  # muss zu __version__ in whisproq.py passen

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

# --- Startmenue-Eintrag (manuell startbar ueber "Alle Apps" -> Whisproq) ---
$lnkPath = Join-Path ([Environment]::GetFolderPath("Programs")) "Whisproq.lnk"
try {
    $ws = New-Object -ComObject WScript.Shell
    $sc = $ws.CreateShortcut($lnkPath)
    $sc.TargetPath = $exe
    $sc.WorkingDirectory = $dst
    $sc.IconLocation = $exe
    $sc.Description = "Whisproq - Push-to-talk-Diktat (Groq)"
    $sc.Save()
    Write-Host "Startmenue-Eintrag angelegt (Alle Apps -> Whisproq)." -ForegroundColor Green
} catch {
    Write-Host "Startmenue-Eintrag nicht anlegbar: $($_.Exception.Message)" -ForegroundColor Yellow
}

# --- Autostart als GEPLANTE AUFGABE (nicht Run-Key) ---
# Der Run-Key feuert beim Windows-"Schnellstart" (Fast Startup / Hybrid-Boot)
# zu frueh und ohne Verzoegerung, bevor Tastatur-/Audio-Treiber re-initialisiert
# sind -> Whisproq startete dann teils gar nicht. Eine Anmelde-getriggerte
# geplante Aufgabe mit kurzer Verzoegerung ueberlebt den Schnellstart robust
# und laeuft auch im Akkubetrieb (Laptop!).
$runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"

function Set-WhisproqAutostart {
    param([string]$Exe)
    # Alten Run-Key-Autostart auf die Aufgabe migrieren
    Remove-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -Name "Whisproq" -ErrorAction SilentlyContinue
    try {
        # WICHTIG: ueber die Shell (explorer.exe) starten, NICHT die EXE direkt.
        # Ein direkt vom Aufgabenplaner erzeugter Prozess haengt nicht sauber an
        # der interaktiven Eingabe-Sitzung -> der globale Low-Level-Tastatur-Hook
        # (WH_KEYBOARD_LL) wird zwar installiert, empfaengt aber KEINE Tasten.
        # explorer.exe erzeugt Whisproq im Shell-/Sitzungskontext -> Hook lebt.
        # Der zuverlaessige Anmelde-Trigger (Schnellstart-fest) bleibt unveraendert.
        $action = New-ScheduledTaskAction -Execute "explorer.exe" -Argument ('"' + $Exe + '"')
        $trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
        $trigger.Delay = "PT15S"                       # Treiber nach Boot bereit
        $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
            -DontStopIfGoingOnBatteries -StartWhenAvailable `
            -ExecutionTimeLimit ([TimeSpan]::Zero)
        $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME `
            -LogonType Interactive -RunLevel Limited
        Register-ScheduledTask -TaskName "Whisproq" -Action $action `
            -Trigger $trigger -Settings $settings -Principal $principal `
            -Description "Startet Whisproq bei der Anmeldung (Schnellstart-fest)." `
            -Force | Out-Null
        return $true
    } catch {
        # Faellt die Aufgaben-Registrierung aus, wenigstens Run-Key setzen
        Set-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -Name "Whisproq" -Value ('"' + $Exe + '"')
        Write-Host "Geplante Aufgabe fehlgeschlagen ($($_.Exception.Message)) - Run-Key als Fallback." -ForegroundColor Yellow
        return $false
    }
}

# hatte der User bisher Autostart (alter Run-Key ODER schon eine Aufgabe)?
$oldRun = Get-ItemProperty -Path $runKey -Name "Whisproq" -ErrorAction SilentlyContinue
$oldTask = Get-ScheduledTask -TaskName "Whisproq" -ErrorAction SilentlyContinue
$hadAuto = ($null -ne $oldRun) -or ($null -ne $oldTask)

if ($update) {
    if ($hadAuto) {
        $ok = Set-WhisproqAutostart -Exe $exe
        if ($ok) { Write-Host "Update: Autostart auf geplante Aufgabe umgestellt (Schnellstart-fest)." -ForegroundColor Green }
    } else {
        Write-Host "Update: kein Autostart (wie bisher)."
    }
} else {
    Write-Host ""
    $auto = Read-Host "Whisproq beim Windows-Start automatisch starten? (j/n)"
    if ($auto -match "^[jJyY]") {
        $ok = Set-WhisproqAutostart -Exe $exe
        if ($ok) { Write-Host "Autostart eingerichtet (geplante Aufgabe, Schnellstart-fest)." -ForegroundColor Green }
    } else {
        Remove-ItemProperty -Path $runKey -Name "Whisproq" -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName "Whisproq" -Confirm:$false -ErrorAction SilentlyContinue
        Write-Host "Kein Autostart - manuell ueber Startmenue (Whisproq) oder: $exe"
    }
}
Start-Process -FilePath $exe
Write-Host ""
Write-Host "=== Fertig! ===" -ForegroundColor Cyan
Write-Host "Hotkey HALTEN -> sprechen -> loslassen. Satzzeichen mitdiktieren:"
Write-Host "  'Komma' , 'Punkt' . 'Fragezeichen' ? 'Ausrufezeichen' ! 'neue Zeile'"
Write-Host "Manuell starten: Startmenue -> Alle Apps -> Whisproq"
Write-Host "Deinstallieren: Windows-Einstellungen -> Apps -> Whisproq"
Write-Host "Log: $dst\whisproq.log"
Start-Sleep -Seconds 6
