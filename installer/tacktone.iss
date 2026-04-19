; TachTone Inno Setup installer script
; Requires: Inno Setup 6 (https://jrsoftware.org/isinfo.php)
; Build: run build_installer.bat from the repo root

#define AppName "TachTone"
#define AppVersion "1.1"
#define AppPublisher "TachTone"
#define AppExeName "TachTone.exe"

[Setup]
AppId={{A3F2D1B0-7C4E-4A9F-8E12-5B6C3D0F1A2E}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
AllowNoIcons=yes
OutputDir=Output
OutputBaseFilename=TachTone_Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked
Name: "startup"; Description: "Start {#AppName} automatically when &Windows starts"; GroupDescription: "Startup:"; Flags: checkedonce

[Files]
; Main app bundle (built by PyInstaller)
Source: "..\dist\TachTone\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; README for Claude Code integration reference
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Registry]
; Add to Windows startup (only if startup task selected)
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
  ValueType: string; ValueName: "{#AppName}"; ValueData: """{app}\{#AppExeName}"""; \
  Flags: uninsdeletevalue; Tasks: startup

[Run]
; Offer to launch TachTone immediately after install
Filename: "{app}\{#AppExeName}"; \
  Description: "Launch {#AppName} now"; \
  Flags: nowait postinstall skipifsilent

; Offer to open README for Claude Code integration setup
Filename: "notepad.exe"; Parameters: """{app}\README.md"""; \
  Description: "View Claude Code integration instructions (README)"; \
  Flags: nowait postinstall skipifsilent unchecked

[UninstallRun]
; Remove startup entry on uninstall (belt-and-suspenders alongside Registry Flags)
Filename: "reg.exe"; \
  Parameters: "delete ""HKCU\Software\Microsoft\Windows\CurrentVersion\Run"" /v ""{#AppName}"" /f"; \
  Flags: runhidden; RunOnceId: "RemoveStartup"
