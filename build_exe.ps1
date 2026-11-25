# Build standalone Windows EXE: dist\OpenClaw-VideoFactory-Setup.exe
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$py = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
if (-not (Test-Path $py)) { $py = (Get-Command python).Source }

if (-not (Test-Path "$root\.build-venv\Scripts\python.exe")) {
  & $py -m venv "$root\.build-venv"
}
$vpy = "$root\.build-venv\Scripts\python.exe"
& $vpy -m pip install --upgrade pip --quiet
& $vpy -m pip install pyinstaller --quiet

& $vpy -m PyInstaller `
  --noconfirm `
  --clean `
  --onefile `
  --windowed `
  --name "OpenClaw-VideoFactory-Setup" `
  --paths "src\installer" `
  --add-data "src\video_factory;src\video_factory" `
  --add-data "src\skill;src\skill" `
  "src\installer\app_gui.py"

Write-Host "`nBUILD SUCCESS:" -ForegroundColor Green
Get-Item "$root\dist\OpenClaw-VideoFactory-Setup.exe" | Select-Object FullName, Length
