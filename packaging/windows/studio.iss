; Inno Setup — Studio Windows Installer (unsigned).
; Komponentenwahl: HD60 und/oder Wave Link Linux.

#define MyAppName "Studio"
#ifndef MyAppVersion
  #define MyAppVersion "dev"
#endif
#define MyAppPublisher "Bavarian4736"
#define MyAppURL "https://github.com/Bavarian4736/studio"

[Setup]
AppId={{A8E3C2D1-9F40-4B6A-8E21-7C0A5B91D304}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
DefaultDirName={localappdata}\Studio
DefaultGroupName=Studio
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\..\dist
OutputBaseFilename=Studio-Windows-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName=Studio
InfoBeforeFile=info-before.txt
LicenseFile=..\..\capture-card\LICENSE

[Languages]
Name: "german"; MessagesFile: "compiler:Languages\German.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Types]
Name: "full"; Description: "Beides (HD60 und Wave Link)"
Name: "hd60only"; Description: "Nur HD60"
Name: "wavelinkonly"; Description: "Nur Wave Link Linux"
Name: "custom"; Description: "Auswahl"; Flags: iscustom

[Components]
Name: "hd60"; Description: "HD60 — Elgato Game Capture HD60 S (Vorschau + Linux-Treiber)"; Types: full hd60only custom
Name: "wavelink"; Description: "Wave Link Linux (Spurwerk) — PipeWire-Mixer"; Types: full wavelinkonly custom

[Files]
; Gemeinsam
Source: "..\..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\install.sh"; DestDir: "{app}"; Flags: ignoreversion
Source: "INSTALL-HINWEIS.txt"; DestDir: "{app}"; Flags: ignoreversion
; HD60
Source: "..\..\capture-card\*"; DestDir: "{app}\capture-card"; Flags: ignoreversion recursesubdirs createallsubdirs; Components: hd60
Source: "..\..\hd60s"; DestDir: "{app}"; Flags: ignoreversion; Components: hd60
; Wave Link
Source: "..\..\wave-link-linux\*"; DestDir: "{app}\wave-link-linux"; Flags: ignoreversion recursesubdirs createallsubdirs; Components: wavelink
Source: "..\..\wavelink-linux"; DestDir: "{app}"; Flags: ignoreversion; Components: wavelink
; Windows-Hilfen
Source: "setup.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "Install.bat"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Studio Ordner öffnen"; Filename: "{app}"
Name: "{group}\GitHub Releases"; Filename: "{#MyAppURL}/releases"
Name: "{group}\Studio deinstallieren"; Filename: "{uninstallexe}"

[Code]
function InitializeWizard: Boolean;
begin
  Result := True;
end;
