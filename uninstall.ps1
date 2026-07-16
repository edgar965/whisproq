# Whisproq - Deinstallation (aufrufbar ueber Windows "Installierte Apps"
# oder direkt). Entfernt Programm, Autostart und Registry-Eintraege.
# -Quiet: ohne Rueckfrage (fuer automatische Aufraeumlaeufe).
param([switch]$Quiet)
$ErrorActionPreference = "SilentlyContinue"
$dst = Join-Path $env:LOCALAPPDATA "Whisproq"

if (-not $Quiet) {
    $a = Read-Host "Whisproq wirklich deinstallieren? (j/n)"
    if ($a -notmatch "^[jJyY]") { exit 0 }
}

# 1) laufende Instanzen beenden (EXE- und Python-Variante)
Get-Process -Name Whisproq | Stop-Process -Force
Get-CimInstance Win32_Process -Filter "Name like 'pythonw%'" |
    Where-Object { $_.CommandLine -like "*whisproq*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Start-Sleep -Milliseconds 800

# 2) Autostart (Run-Key + geplante Aufgabe), Startmenue-Eintrag und
#    "Installierte Apps"-Eintrag entfernen
Remove-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -Name "Whisproq"
Unregister-ScheduledTask -TaskName "Whisproq" -Confirm:$false
Remove-Item -Path (Join-Path ([Environment]::GetFolderPath("Programs")) "Whisproq.lnk") -Force
Remove-Item -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\Whisproq" -Recurse

# 3) Programmordner loeschen (PowerShell hat das Skript bereits komplett
#    geladen - die eigene Datei darf mit weg)
Set-Location $env:USERPROFILE
Remove-Item -Path $dst -Recurse -Force

Write-Host ""
Write-Host "Whisproq wurde deinstalliert." -ForegroundColor Green
Write-Host "Hinweis: der GROQ_API_KEY bleibt gesetzt (koennte von anderen"
Write-Host "Programmen genutzt werden). Entfernen: Umgebungsvariablen-Dialog"
Write-Host "oder: reg delete HKCU\Environment /v GROQ_API_KEY /f"
if (-not $Quiet) { Start-Sleep -Seconds 4 }
