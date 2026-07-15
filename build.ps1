# =====================================================================
# Whisproq - baut die verteilbare Setup-EXE (Whisproq_Setup.exe).
# Voraussetzung: venv vorhanden (install.bat) + PyInstaller:
#   venv\Scripts\pip install pyinstaller
# Ablauf: PyInstaller onedir -> Zip (Python, s. build\make_zip.py) ->
#         SED generieren (absolute Pfade) -> IExpress-SFX.
# =====================================================================
$ErrorActionPreference = "Stop"
$HERE = Split-Path -Parent $MyInvocation.MyCommand.Path
$py = Join-Path $HERE "venv\Scripts\python.exe"
if (-not (Test-Path $py)) { throw "venv fehlt - erst install.bat ausfuehren, dann: venv\Scripts\pip install pyinstaller" }

Write-Host "1/4 PyInstaller (onedir, noconsole) ..." -ForegroundColor Cyan
& $py -m PyInstaller --noconfirm --onedir --noconsole --name Whisproq `
    --distpath (Join-Path $HERE "dist") `
    --workpath (Join-Path $HERE "build\pyi") `
    --specpath (Join-Path $HERE "build") `
    (Join-Path $HERE "whisproq.py")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller fehlgeschlagen (Exit $LASTEXITCODE)" }
Copy-Item (Join-Path $HERE "config.json") (Join-Path $HERE "dist\Whisproq\") -Force
Copy-Item (Join-Path $HERE "uninstall.ps1") (Join-Path $HERE "dist\Whisproq\") -Force

Write-Host "2/4 Payload-Zip (Python-zipfile) ..." -ForegroundColor Cyan
& $py (Join-Path $HERE "build\make_zip.py")
if ($LASTEXITCODE -ne 0) { throw "Zip fehlgeschlagen" }

Write-Host "3/4 SED generieren ..." -ForegroundColor Cyan
# IExpress braucht absolute Pfade -> SED wird hier erzeugt, nicht committet.
$sed = @"
[Version]
Class=IEXPRESS
SEDVersion=3
[Options]
PackagePurpose=InstallApp
ShowInstallProgramWindow=1
HideExtractAnimation=1
UseLongFileName=1
InsideCompressed=0
CAB_FixedSize=0
CAB_ResvCodeSigning=0
RebootMode=N
InstallPrompt=%InstallPrompt%
DisplayLicense=%DisplayLicense%
FinishMessage=%FinishMessage%
TargetName=%TargetName%
FriendlyName=%FriendlyName%
AppLaunched=%AppLaunched%
PostInstallCmd=%PostInstallCmd%
AdminQuietInstCmd=%AdminQuietInstCmd%
UserQuietInstCmd=%UserQuietInstCmd%
SourceFiles=SourceFiles
[Strings]
InstallPrompt=
DisplayLicense=
FinishMessage=
TargetName=$HERE\Install\Whisproq_Setup.exe
FriendlyName=Whisproq Setup
AppLaunched=powershell.exe -NoProfile -ExecutionPolicy Bypass -File setup.ps1
PostInstallCmd=<None>
AdminQuietInstCmd=
UserQuietInstCmd=
FILE0="Whisproq.zip"
FILE1="setup.ps1"
[SourceFiles]
SourceFiles0=$HERE\build\payload\
[SourceFiles0]
%FILE0%=
%FILE1%=
"@
$sedPath = Join-Path $HERE "build\Whisproq_Setup.sed"
Set-Content -Path $sedPath -Value $sed -Encoding Ascii

Write-Host "4/4 IExpress ..." -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path (Join-Path $HERE "Install") | Out-Null
# IExpress bricht mit Exit 1 ab, wenn die Ziel-EXE schon existiert -> loeschen.
Remove-Item (Join-Path $HERE "Install\Whisproq_Setup.exe") -Force -ErrorAction SilentlyContinue
Start-Process -FilePath "iexpress.exe" -ArgumentList "/N", "/Q", $sedPath -Wait -NoNewWindow
$exe = Join-Path $HERE "Install\Whisproq_Setup.exe"
if (-not (Test-Path $exe)) { throw "IExpress hat keine EXE erzeugt - SED pruefen: $sedPath" }
$mb = [math]::Round((Get-Item $exe).Length / 1MB, 1)
Write-Host "OK: Whisproq_Setup.exe gebaut ($mb MB)." -ForegroundColor Green
