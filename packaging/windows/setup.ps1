# Studio Windows Installer — Programmauswahl (HD60 / Wave Link) und Dateipaket.
#Requires -Version 5.1
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
# Wenn aus dist\payload gestartet: Root ist payload
if (-not (Test-Path (Join-Path $Root "capture-card"))) {
  $Parent = Split-Path -Parent $Root
  if (Test-Path (Join-Path $Parent "capture-card")) {
    $Root = $Parent
  }
}

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$form = New-Object System.Windows.Forms.Form
$form.Text = "Studio Installer"
$form.Size = New-Object System.Drawing.Size(480, 360)
$form.StartPosition = "CenterScreen"
$form.FormBorderStyle = "FixedDialog"
$form.MaximizeBox = $false

$title = New-Object System.Windows.Forms.Label
$title.Text = "Studio"
$title.Font = New-Object System.Drawing.Font("Segoe UI", 16, [System.Drawing.FontStyle]::Bold)
$title.Location = New-Object System.Drawing.Point(20, 16)
$title.AutoSize = $true
$form.Controls.Add($title)

$info = New-Object System.Windows.Forms.Label
$info.Text = "Wähle die Programme. Beide laufen vollständig nur unter Linux (Nobara/Fedora). Unter Windows wird ein Dateipaket nach %LOCALAPPDATA%\Studio kopiert."
$info.Location = New-Object System.Drawing.Point(20, 56)
$info.Size = New-Object System.Drawing.Size(420, 60)
$form.Controls.Add($info)

$cbHd60 = New-Object System.Windows.Forms.CheckBox
$cbHd60.Text = "HD60 — Elgato Game Capture HD60 S (Vorschau + Linux-Treiber)"
$cbHd60.Checked = $true
$cbHd60.Location = New-Object System.Drawing.Point(24, 130)
$cbHd60.Size = New-Object System.Drawing.Size(420, 30)
$form.Controls.Add($cbHd60)

$cbWave = New-Object System.Windows.Forms.CheckBox
$cbWave.Text = "Wave Link Linux (Spurwerk) — PipeWire-Mixer"
$cbWave.Checked = $true
$cbWave.Location = New-Object System.Drawing.Point(24, 170)
$cbWave.Size = New-Object System.Drawing.Size(420, 30)
$form.Controls.Add($cbWave)

$ok = New-Object System.Windows.Forms.Button
$ok.Text = "Installieren"
$ok.Location = New-Object System.Drawing.Point(240, 260)
$ok.Size = New-Object System.Drawing.Size(100, 30)
$form.Controls.Add($ok)

$cancel = New-Object System.Windows.Forms.Button
$cancel.Text = "Abbrechen"
$cancel.Location = New-Object System.Drawing.Point(350, 260)
$cancel.Size = New-Object System.Drawing.Size(100, 30)
$form.CancelButton = $cancel
$form.Controls.Add($cancel)

$script:DoInstall = $false
$ok.Add_Click({
  if (-not $cbHd60.Checked -and -not $cbWave.Checked) {
    [System.Windows.Forms.MessageBox]::Show("Bitte mindestens ein Programm wählen.", "Studio") | Out-Null
    return
  }
  $script:DoInstall = $true
  $form.Close()
})
$cancel.Add_Click({ $form.Close() })

[void]$form.ShowDialog()
if (-not $script:DoInstall) { exit 0 }

$Dest = Join-Path $env:LOCALAPPDATA "Studio"
New-Item -ItemType Directory -Force -Path $Dest | Out-Null

function Copy-Tree($Src, $Dst) {
  if (Test-Path $Dst) { Remove-Item -Recurse -Force $Dst }
  Copy-Item -Recurse -Force $Src $Dst
}

# README immer
foreach ($name in @("README.md", "install.sh")) {
  $src = Join-Path $Root $name
  if (Test-Path $src) { Copy-Item -Force $src (Join-Path $Dest $name) }
}

if ($cbHd60.Checked) {
  Copy-Tree (Join-Path $Root "capture-card") (Join-Path $Dest "capture-card")
  $launcher = Join-Path $Root "hd60s"
  if (Test-Path $launcher) { Copy-Item -Force $launcher (Join-Path $Dest "hd60s") }
}
if ($cbWave.Checked) {
  Copy-Tree (Join-Path $Root "wave-link-linux") (Join-Path $Dest "wave-link-linux")
  $launcher = Join-Path $Root "wavelink-linux"
  if (Test-Path $launcher) { Copy-Item -Force $launcher (Join-Path $Dest "wavelink-linux") }
}

$hint = @"
Studio — Windows-Dateipaket
===========================

Ziel: $Dest

Unter Linux (Nobara/Fedora) im Ordner:
  ./install.sh

Oder den Linux-Installer von GitHub Releases nutzen:
https://github.com/Bavarian4736/studio/releases
"@
Set-Content -Path (Join-Path $Dest "INSTALL-HINWEIS.txt") -Value $hint -Encoding UTF8

[System.Windows.Forms.MessageBox]::Show("Dateien nach:`n$Dest`n`nVollständige Installation nur unter Linux (Nobara/Fedora).", "Studio") | Out-Null
Write-Host "Fertig: $Dest"
