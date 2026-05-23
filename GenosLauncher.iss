; Inno Setup script for GenosLauncher
; Requires Inno Setup 6.x — https://jrsoftware.org/isinfo.php
; Build from command line: iscc GenosLauncher.iss

#define AppName        "GenosLauncher"
#ifndef AppVersion
  #error AppVersion must be passed by the build script, e.g. iscc /DAppVersion=0.2.0 GenosLauncher.iss
#endif
#define AppPublisher   "GenosLauncher Contributors"
#define AppURL         "https://github.com/csgenos/genoslauncher"
#define AppExeName     "GenosLauncher.exe"
#define BuildDir       "dist\GenosLauncher"

[Setup]
AppId={{F4A1C2D3-8B9E-4F0A-B2C1-D3E4F5A6B7C8}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases

; Installation directory — LocalAppData means no UAC prompt (like Discord, Slack, Cursor)
DefaultDirName={localappdata}\{#AppName}
DefaultGroupName={#AppName}
AllowNoIcons=yes

; Output
OutputDir=installer_output
OutputBaseFilename=GenosLauncher-{#AppVersion}-Setup
#ifexist "assets\icon.ico"
SetupIconFile=assets\icon.ico
#endif
UninstallDisplayIcon={app}\{#AppExeName}

; Compression — solid mode disabled so files extract directly to the
; destination rather than via a temp directory, avoiding a window where
; security software can intercept Qt DLLs before the exclusion applies.
Compression=lzma2/fast
SolidCompression=no

; No admin required — installs per-user into LocalAppData
PrivilegesRequired=lowest

; Windows 10 1809+ required for modern APIs
MinVersion=10.0.17763

; Appearance
WizardStyle=modern
WizardSizePercent=120
DisableWelcomePage=no
#ifexist "LICENSE"
LicenseFile=LICENSE
#endif

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "quicklaunchicon"; Description: "{cm:CreateQuickLaunchIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked; OnlyBelowVersion: 6.1

[Files]
; Main application directory (entire onedir build output)
Source: "{#BuildDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; Start Menu
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"

; Desktop (optional)
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

; Quick Launch (legacy Windows XP/Vista, optional)
Name: "{userappdata}\Microsoft\Internet Explorer\Quick Launch\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: quicklaunchicon

[Run]
; Offer to launch after install
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(AppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Remove user-data directory only if it exists and user agrees (leave data by default)
; Type: filesandordirs; Name: "{localappdata}\GenosLauncher"

[Code]
// Optional: check for existing installation and warn if downgrading
function InitializeSetup(): Boolean;
begin
  Result := True;
end;
