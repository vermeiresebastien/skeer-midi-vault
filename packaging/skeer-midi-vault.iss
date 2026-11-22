; SKEER MIDI VAULT - per-user Windows installer. Release number: see AppVersion.
; Build with: iscc packaging\skeer-midi-vault.iss
; The app is self-contained (Python runtime + interface bundled). It opens the
; local application in the user's browser and leaves a tray icon / Settings quit.
; User library data stays in %LOCALAPPDATA%\Skeer\MIDI Vault and is not removed.

#define AppName "SKEER MIDI VAULT"
#define AppVersion "1.1.2"
#define AppPublisher "SKEER AUDIO"
#define AppExeName "SKEER MIDI VAULT.exe"
#ifndef SourceRoot
; Overridable with ISCC /DSourceRoot=<path>, which is how a probe compile reads the real
; launch/ folder from a temporary output directory. Left alone it is the repo root.
#define SourceRoot ".."
#endif
#define AppId "{{B7E2D5A8-9F3F-4C7B-B62B-5E7B59A3C1D4}"

[Setup]
AppId={#AppId}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
VersionInfoVersion=1.1.2.0
VersionInfoCompany={#AppPublisher}
VersionInfoCopyright=Copyright (C) 2026 SKEER AUDIO. All rights reserved.
VersionInfoDescription={#AppName} installer
VersionInfoOriginalFileName=SKEER-MIDI-VAULT-Setup-{#AppVersion}.exe
VersionInfoProductName={#AppName}
VersionInfoProductVersion={#AppVersion}
VersionInfoTextVersion={#AppVersion}
DefaultDirName={autopf}\SKEER MIDI VAULT
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
; The Start Menu entry is a task so that it can be declined. With no Tasks flag it is created on
; every install, which lets a folder Setup is not allowed to write abort the whole installation
; after the payload is already copied - and /NOICONS does not help a {autoprograms} path, only a
; {group} one. Measured on Inno Setup 6.7.4.
Name: "startmenuicon"; Description: "Create a Start Menu shortcut"; GroupDescription: "Additional shortcuts:"
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: checkedonce

[Code]
// The plug-in copy that lands in the all-users folder only exists in an all-users install, and
// this is the one place that says so - in the Setup log, where a failed install is diagnosed.
// The per-user install never touches a shared folder; it leaves the bundle beside the app and
// names the folder a host can be pointed at. Since 1.1.2 the mirror is true as well: an all-users
// install writes the shared folder and declines the copy beside the app, so neither mode leaves
// two bundles with one class ID on the machine.
// Comments here must be Pascal-style: in the [Code] section a semicolon comment is not a
// comment, it is a syntax error ("'BEGIN' expected"), because the section is handed to the
// script compiler rather than read as an ini-style list. Measured on Inno Setup 6.7.4.
function CommonVst3: Boolean;
begin
  Result := IsAdminInstallMode;
  if Result then
    Log('VST3: installing into ' + ExpandConstant('{commoncf64}\VST3') + ' only. The copy under ' +
        ExpandConstant('{app}\VST3') + ' is declined in an all-users install, so this machine holds ' +
        'one bundle with this class ID.')
  else
    Log('VST3: installed only in ' + ExpandConstant('{app}\VST3') + ' because this is a ' +
        'per-user install; the all-users plug-in folder was not touched. Re-run Setup with ' +
        '/ALLUSERS to place the bundle where every host looks by default, or point the host ' +
        'at that folder.');
end;

[Files]
Source: "{#SourceRoot}\launch\SKEER MIDI VAULT\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
#ifdef PluginStaged
; Staged by packaging\build_installer.ps1, which refuses to ship a bundle whose moduleinfo.json
; disagrees with AppVersion. Compiling without /DPluginStaged makes an installer with no plug-in
; in it, which is what -SkipPlugin needs to keep working instead of failing on a missing Source.
; One bundle per install mode. The shared-folder entry below carries Check: CommonVst3, so before
; 1.1.2 an all-users install copied this entry as well and left two byte-identical bundles on disk.
; That was quiet in practice only because of which folders this machine's host scans: measured
; 2026-11-22, Live wrote exactly one module row and one device row for the SkAuMvlt class ID while
; both copies sat there, and {app}\VST3 is not among the paths its scan log names. A host that does
; scan its own plug-in folder, or a user who adds {app}\VST3, would list the same plug-in twice with
; nothing to tell them which one a saved project is using. Declining the entry below in all-users
; mode is what makes that impossible rather than unlikely.
Source: "{#SourceRoot}\launch\VST3\*"; DestDir: "{app}\VST3"; Flags: recursesubdirs createallsubdirs ignoreversion; Check: not CommonVst3
; {commoncf64} is Common Files; {commonpf64} is plain Program Files, and C:\Program Files\VST3 is
; not a folder hosts scan by default. The 64-bit constant rather than {commoncf}: the staged bundle
; is x86_64-win, and {commoncf64} stays right whichever install mode Setup runs in.
Source: "{#SourceRoot}\launch\VST3\*"; DestDir: "{commoncf64}\VST3"; Flags: recursesubdirs createallsubdirs ignoreversion; Check: CommonVst3
#endif

[Icons]
Name: "{autoprograms}\SKEER AUDIO\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; Tasks: startmenuicon; Comment: "SKEER MIDI VAULT local MIDI library"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon; Comment: "SKEER MIDI VAULT local MIDI library"

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch SKEER MIDI VAULT"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{cmd}"; Parameters: "/C taskkill /IM ""{#AppExeName}"" /T /F >nul 2>&1"; Flags: runhidden; RunOnceId: "StopSkeerMidiVault"

[UninstallDelete]
; The application folder is removed by the uninstaller. The user library in
; %LOCALAPPDATA%\Skeer\MIDI Vault is intentionally left untouched.
Type: filesandordirs; Name: "{app}\_internal"
