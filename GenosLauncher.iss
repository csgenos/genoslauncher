; Inno Setup script for GenosLauncher
; Requires Inno Setup 6.x — https://jrsoftware.org/isinfo.php
; Build from command line: iscc GenosLauncher.iss

#define AppName        "GenosLauncher"
#define AppVersion     "0.2.0"
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

; Installation directory
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
AllowNoIcons=yes

; Output
OutputDir=installer_output
OutputBaseFilename=GenosLauncher-{#AppVersion}-Setup
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\{#AppExeName}

; Compression
Compression=lzma2/ultra64
SolidCompression=yes
LZMANumBlockThreads=4

; Require admin for Program Files install
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog

; Windows version requirement (Windows 10+)
MinVersion=10.0.17763

; Appearance
WizardStyle=modern
WizardSizePercent=120
DisableWelcomePage=no
LicenseFile=LICENSE

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
