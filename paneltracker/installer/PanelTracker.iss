; Draft installer Inno Setup (untuk tahap berikutnya)
; Compile: install Inno Setup 6, buka file ini, tekan Compile (Ctrl+F9)
; Saat ter-install di Program Files, data otomatis disimpan di Documents\PanelTracker
#define AppName "Panel Tracker"
#define AppVersion "2.9.1"
#define AppExe "PanelTracker.exe"

[Setup]
AppId={{6F1C2B7E-4E1A-4C59-9B7E-3A0D5C2F9A11}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Panel Tracker
DefaultDirName={autopf}\PanelTracker
DefaultGroupName={#AppName}
OutputDir=..\dist
OutputBaseFilename=PanelTracker_Setup_{#AppVersion}
SetupIconFile=..\assets\icon.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\{#AppExe}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
