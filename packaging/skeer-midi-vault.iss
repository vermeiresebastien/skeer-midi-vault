; SKEER MIDI VAULT 1.0.0 - per-user Windows installer.
; Build with: iscc packaging\skeer-midi-vault.iss
; The app is self-contained (Python runtime + interface bundled). It opens the
; local application in the user's browser and leaves a tray icon / Settings quit.
; User library data stays in %LOCALAPPDATA%\Skeer\MIDI Vault and is not removed.

#define AppName "SKEER MIDI VAULT"
#define AppVersion "1.0.0"
#define AppPublisher "SKEER AUDIO"
#define AppExeName "SKEER MIDI VAULT.exe"
#define SourceRoot ".."
#define AppId "{{B7E2D5A8-9F3F-4C7B-B62B-5E7B59A3C1D4}"

[Setup]
AppId={#AppId}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
VersionInfoVersion=1.0.0.0
VersionInfoCompany={#AppPublisher}
VersionInfoCopyright=Copyright (C) 2026 SKEER AUDIO. All rights reserved.
VersionInfoDescription={#AppName} installer
VersionInfoOriginalFileName=SKEER-MIDI-VAULT-Setup-{#AppVersion}.exe
VersionInfoProductName={#AppName}
VersionInfoProductVersion={#AppVersion}
VersionInfoTextVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\SKEER MIDI VAULT
DefaultGroupName=SKEER AUDIO
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=commandline
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#SourceRoot}\launch
OutputBaseFilename=SKEER-MIDI-VAULT-Setup-{#AppVersion}
SetupIconFile={#SourceRoot}\build\app.ico
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName}
LicenseFile={#SourceRoot}\packaging\EULA.txt
Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes
WizardStyle=modern
SetupLogging=yes
CloseApplications=yes
RestartApplications=no
AppMutex=Local\SkeerMidiVaultDesktopV1
UsePreviousAppDir=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: checkedonce

[Files]
Source: "{#SourceRoot}\launch\SKEER MIDI VAULT\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\SKEER AUDIO\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; Comment: "SKEER MIDI VAULT local MIDI library"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon; Comment: "SKEER MIDI VAULT local MIDI library"

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch SKEER MIDI VAULT"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{cmd}"; Parameters: "/C taskkill /IM ""{#AppExeName}"" /T /F >nul 2>&1"; Flags: runhidden; RunOnceId: "StopSkeerMidiVault"

[UninstallDelete]
; The application folder is removed by the uninstaller. The user library in
; %LOCALAPPDATA%\Skeer\MIDI Vault is intentionally left untouched.
Type: filesandordirs; Name: "{app}\_internal"
