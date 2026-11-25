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

$ver = "v" + (Get-Date -Format "dd.MM.yyyy")
$exeName = "OpenClaw-VideoFactory-Setup-$ver"

& $vpy -m PyInstaller `
  --noconfirm `
  --clean `
  --onefile `
  --windowed `
  --name $exeName `
  --paths "src\installer" `
  --add-data "src\video_factory;src\video_factory" `
  --add-data "src\skill;src\skill" `
  --add-data "src\installer\app_oauth_config.json;src\installer" `
  "src\installer\app_gui.py"

Write-Host "`nBUILD SUCCESS ($ver):" -ForegroundColor Green
Get-Item "$root\dist\$exeName.exe" | Select-Object FullName, Length
