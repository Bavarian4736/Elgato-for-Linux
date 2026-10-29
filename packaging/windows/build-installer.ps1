# Baut Studio-Windows-Setup.exe (Inno Setup) und Fallback-ZIP.
param(
  [string]$OutDir = "",
  [string]$Version = $env:STUDIO_VERSION
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
if (-not $OutDir) { $OutDir = Join-Path $Root "dist" }
if (-not $Version) { $Version = "dev" }

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

# --- Fallback-ZIP immer ---
$Stage = Join-Path $env:TEMP ("studio-win-" + [guid]::NewGuid().ToString("n"))
$Payload = Join-Path $Stage "Studio"
New-Item -ItemType Directory -Force -Path $Payload | Out-Null

$robocopy = {
  param($Src, $Dst)
  New-Item -ItemType Directory -Force -Path $Dst | Out-Null
  & robocopy $Src $Dst /E /NFL /NDL /NJH /NJS /nc /ns /np `
    /XD .git dist __pycache__ .venv venv `
    /XF *.pyc | Out-Null
  # robocopy exit 0-7 = success
  if ($LASTEXITCODE -ge 8) { throw "robocopy failed: $LASTEXITCODE" }
  $global:LASTEXITCODE = 0
}

& $robocopy (Join-Path $Root "capture-card") (Join-Path $Payload "capture-card")
& $robocopy (Join-Path $Root "wave-link-linux") (Join-Path $Payload "wave-link-linux")
Copy-Item (Join-Path $Root "README.md") $Payload -Force
Copy-Item (Join-Path $Root "install.sh") $Payload -Force
Copy-Item (Join-Path $Root "hd60s") $Payload -Force
Copy-Item (Join-Path $Root "wavelink-linux") $Payload -Force
Copy-Item (Join-Path $Root "packaging\windows\setup.ps1") $Payload -Force
Copy-Item (Join-Path $Root "packaging\windows\Install.bat") $Payload -Force
Copy-Item (Join-Path $Root "packaging\windows\INSTALL-HINWEIS.txt") $Payload -Force

$Zip = Join-Path $OutDir "Studio-Windows-Installer.zip"
if (Test-Path $Zip) { Remove-Item $Zip -Force }
Compress-Archive -Path $Payload -DestinationPath $Zip -Force
Write-Host "Geschrieben: $Zip"

# --- Inno Setup .exe, wenn ISCC verfügbar ---
$Iscc = $null
foreach ($cand in @(
  "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
  "${env:LocalAppData}\Programs\Inno Setup 6\ISCC.exe",
  "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
)) {
  if (Test-Path $cand) { $Iscc = $cand; break }
}

if (-not $Iscc) {
  Write-Host "Inno Setup nicht gefunden — versuche Download…"
  $InnoSetup = Join-Path $env:TEMP "innosetup-install.exe"
  Invoke-WebRequest -Uri "https://jrsoftware.org/download.php/is.exe" -OutFile $InnoSetup
  Start-Process -FilePath $InnoSetup -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART" -Wait
  foreach ($cand in @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
  )) {
    if (Test-Path $cand) { $Iscc = $cand; break }
  }
}

if ($Iscc) {
  $Iss = Join-Path $Root "packaging\windows\studio.iss"
  & $Iscc /DMyAppVersion=$Version $Iss
  $Exe = Join-Path $OutDir "Studio-Windows-Setup.exe"
  if (-not (Test-Path $Exe)) { throw "Inno Setup hat keine EXE erzeugt." }
  Write-Host "Geschrieben: $Exe"
} else {
  Write-Warning "Kein Inno Setup — nur ZIP gebaut. CI sollte ISCC bereitstellen."
}

Remove-Item -Recurse -Force $Stage -ErrorAction SilentlyContinue
