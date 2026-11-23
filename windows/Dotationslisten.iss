; Inno Setup script - built by windows\build_windows.ps1 (ISCC /DAppVersion=x.y.z /DRoot=<repo>)
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef Root
  #define Root ".."
#endif

[Setup]
AppId={{6F0B1C2E-6D49-4F57-9C1E-0D7A5B3C9E21}
AppName=Dotationslisten
AppVersion={#AppVersion}
AppVerName=Dotationslisten {#AppVersion}
AppPublisher=Robin Valley
AppCopyright=Copyright (c) Robin Valley. Alle Rechte vorbehalten.
AppPublisherURL=https://buymeacoffee.com/rvalley98
; per user, no administrator rights needed
PrivilegesRequired=lowest
DefaultDirName={autopf}\Dotationslisten
DefaultGroupName=Dotationslisten
DisableProgramGroupPage=yes
OutputBaseFilename=Dotationslisten-Setup-{#AppVersion}
SetupIconFile={#Root}\windows\build\Dotationslisten.ico
UninstallDisplayIcon={app}\Dotationslisten.exe
LicenseFile={#Root}\windows\build\LICENSE.txt
InfoAfterFile={#Root}\windows\build\INSTALLATION.txt
Compression=lzma2/max
SolidCompression=yes
; Ollama with the Nvidia libraries is >1 GB: compress in parallel
LZMAUseSeparateProcess=yes
LZMANumBlockThreads=4
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
CloseApplications=yes

[Languages]
Name: "de"; MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "desktopicon"; Description: "Verknüpfung auf dem Desktop"; Flags: unchecked
Name: "autostart"; Description: "Beim Anmelden automatisch starten (z. B. für den Scanner-Ordner)"; Flags: unchecked

[Files]
Source: "{#Root}\windows\dist\Dotationslisten\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#Root}\windows\build\INSTALLATION.txt"; DestDir: "{app}"; DestName: "Installation.txt"
Source: "{#Root}\windows\build\THIRD_PARTY_LICENSES.txt"; DestDir: "{app}"; DestName: "Lizenzen Dritter.txt"

[Icons]
Name: "{group}\Dotationslisten"; Filename: "{app}\Dotationslisten.exe"
Name: "{group}\Dotationslisten deinstallieren"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Dotationslisten"; Filename: "{app}\Dotationslisten.exe"; Tasks: desktopicon
Name: "{userstartup}\Dotationslisten"; Filename: "{app}\Dotationslisten.exe"; Tasks: autostart

[Run]
Filename: "{app}\Dotationslisten.exe"; Description: "Dotationslisten jetzt starten"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{cmd}"; Parameters: "/C taskkill /IM Dotationslisten.exe /F"; Flags: runhidden; RunOnceId: "StopApp"
; the bundled Ollama normally ends with the app; only ours (in {app}), never an Ollama the user installed
Filename: "powershell.exe"; Parameters: "-NoProfile -Command ""Get-Process ollama -ErrorAction SilentlyContinue | Where-Object {{ $_.Path -like '{app}\*' } | Stop-Process -Force"""; Flags: runhidden; RunOnceId: "StopOllama"
; the data folder (Dokumente\Dotationslisten) and the downloaded model (%USERPROFILE%\.ollama) are never
; touched by the uninstaller
