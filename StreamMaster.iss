; StreamMaster v2.0 — Inno Setup installer script
; Requires Inno Setup 6.x: https://jrsoftware.org/isinfo.php
;
; To build: open this file in Inno Setup Compiler and click Build
; Output: Output\StreamMaster_Setup_v2.0.exe

#define AppName      "StreamMaster"
#define AppVersion   "2.0.5"
#define AppPublisher "IVibeStuff"
#define AppURL       "https://github.com/IVibeStuff/StreamMaster"
#define AppExeName   "Launch_Silent.vbs"
#define AppInstDir   "{localappdata}\StreamMaster"

[Setup]
AppId={{A7B3C2D1-4E5F-6789-ABCD-EF0123456789}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} v{#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases
DefaultDirName={#AppInstDir}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=Output
OutputBaseFilename=StreamMaster_Setup_v{#AppVersion}
SetupIconFile=
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
WizardSizePercent=120
DisableWelcomePage=no
LicenseFile=
MinVersion=10.0
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=commandline
UninstallDisplayName={#AppName} v{#AppVersion}
UninstallDisplayIcon={app}\logo.svg
ChangesAssociations=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"
Name: "demucs";      Description: "Install &Stem Separation (Demucs) — adds ~300 MB download on first use, enables Stem Master and advanced Repair"; GroupDescription: "Optional components:"; Flags: unchecked

[Files]
; Core application files
Source: "index.html";             DestDir: "{app}"; Flags: ignoreversion
Source: "server.py";              DestDir: "{app}"; Flags: ignoreversion
Source: "spotify_master.py";      DestDir: "{app}"; Flags: ignoreversion
Source: "mastering_extras.py";    DestDir: "{app}"; Flags: ignoreversion
Source: "vocalride.py";           DestDir: "{app}"; Flags: ignoreversion
Source: "analyser.py";            DestDir: "{app}"; Flags: ignoreversion
Source: "previewer.py";           DestDir: "{app}"; Flags: ignoreversion
Source: "history.py";             DestDir: "{app}"; Flags: ignoreversion
Source: "updater.py";             DestDir: "{app}"; Flags: ignoreversion
Source: "dejinx.py";              DestDir: "{app}"; Flags: ignoreversion
Source: "qc.py";                  DestDir: "{app}"; Flags: ignoreversion
Source: "splice.py";              DestDir: "{app}"; Flags: ignoreversion
Source: "heal.py";                DestDir: "{app}"; Flags: ignoreversion
Source: "levelbridge.py";         DestDir: "{app}"; Flags: ignoreversion
Source: "repair.py";              DestDir: "{app}"; Flags: ignoreversion
Source: "stem_master.py";         DestDir: "{app}"; Flags: ignoreversion
Source: "requirements.txt";       DestDir: "{app}"; Flags: ignoreversion
Source: "Launch.bat";             DestDir: "{app}"; Flags: ignoreversion
Source: "Launch_Silent.vbs";      DestDir: "{app}"; Flags: ignoreversion
Source: "logo.svg";               DestDir: "{app}"; Flags: ignoreversion
Source: "docs\logo_hero.png";     DestDir: "{app}\docs"; Flags: ignoreversion
Source: "README.md";              DestDir: "{app}"; Flags: ignoreversion
Source: "CHANGELOG.md";           DestDir: "{app}"; Flags: ignoreversion

[Icons]
; Start Menu
Name: "{group}\{#AppName}";           Filename: "{sys}\wscript.exe"; Parameters: """{app}\Launch_Silent.vbs"""; Comment: "Launch StreamMaster (silent)"
Name: "{group}\{#AppName} (console)"; Filename: "{app}\Launch.bat";  Comment: "Launch StreamMaster with console (for debugging)"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"

; Desktop shortcut (optional)
Name: "{autodesktop}\{#AppName}"; Filename: "{sys}\wscript.exe"; Parameters: """{app}\Launch_Silent.vbs"""; Comment: "Launch StreamMaster"; Tasks: desktopicon

[Run]
; Install Python packages after copying files
Filename: "python"; Parameters: "-m pip install flask flask-cors pyloudnorm soundfile scipy numpy matchering --quiet --disable-pip-version-check"; \
  WorkingDir: "{app}"; StatusMsg: "Installing StreamMaster packages..."; \
  Flags: runhidden waituntilterminated

; Install Demucs if selected
Filename: "python"; Parameters: "-m pip install demucs --quiet --disable-pip-version-check"; \
  WorkingDir: "{app}"; StatusMsg: "Installing Stem Separation (Demucs)..."; \
  Flags: runhidden waituntilterminated; Tasks: demucs

; Launch StreamMaster after install (offer)
Filename: "{sys}\wscript.exe"; Parameters: """{app}\Launch_Silent.vbs"""; \
  Description: "Launch {#AppName} now"; Flags: nowait postinstall skipifsilent
[UninstallRun]
; Nothing to stop — server is not a service, user may have closed it already

[UninstallDelete]
; Remove all app files but prompt to keep history
Type: filesandordirs; Name: "{app}\.update_cache.json"

[Code]
var
  PythonFound: Boolean;

function InitializeSetup(): Boolean;
var
  ResultCode: Integer;
begin
  // Check Python 3.10+ is installed
  PythonFound := Exec('python', '--version', '', SW_HIDE, ewWaitUntilTerminated, ResultCode)
                 and (ResultCode = 0);

  if not PythonFound then begin
    if MsgBox('Python 3.10 or later is required but was not found on this machine.' + #13#10 + #13#10 +
              'Download Python from python.org and run the installer.' + #13#10 +
              'Tick "Add Python to PATH" before clicking Install.' + #13#10 + #13#10 +
              'Would you like to open the Python download page now?',
              mbConfirmation, MB_YESNO) = IDYES then begin
      ShellExec('open', 'https://www.python.org/downloads/', '', '', SW_SHOWNORMAL, ewNoWait, ResultCode);
    end;
    Result := False;
  end else begin
    Result := True;
  end;
end;

function InitializeUninstall(): Boolean;
var
  HistoryFile: String;
  Response:    Integer;
begin
  HistoryFile := ExpandConstant('{app}\history.json');
  if FileExists(HistoryFile) then begin
    Response := MsgBox('StreamMaster has mastering history saved.' + #13#10 + #13#10 +
                       'Would you like to keep history.json so you can restore it later?',
                       mbConfirmation, MB_YESNO);
    if Response = IDNO then
      DeleteFile(HistoryFile);
  end;
  Result := True;
end;
