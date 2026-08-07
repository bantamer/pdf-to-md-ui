; Inno Setup script for the PDF to Markdown converter.
;
; Produces a single Setup.exe that installs the app, the bundled JRE and a
; desktop shortcut. Compile with:  iscc installer.iss
;
; Expects the PyInstaller output in dist\PDF to Markdown\ and a trimmed
; runtime in jre\ (see BUILD.md).

#define AppName "PDF to Markdown"
#define AppExe "PDF to Markdown.exe"

; CI passes the version with /DAppVersion=...; this is the local fallback.
#ifndef AppVersion
  #define AppVersion "0.0.0-dev"
#endif

[Setup]
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
OutputBaseFilename=PDF-to-Markdown-Setup
Compression=lzma2/max
SolidCompression=yes
; Per-user install needs no admin rights, which avoids a UAC prompt.
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Ярлыки:"

[Files]
Source: "dist\{#AppName}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "jre\*"; DestDir: "{app}\jre"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Запустить {#AppName}"; Flags: nowait postinstall skipifsilent
