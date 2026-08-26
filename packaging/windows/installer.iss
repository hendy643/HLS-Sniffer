; Inno Setup script for hls-sniffer.
;
; Build with: python packaging/build.py gui --onedir  (and cli, onefile)
; then:       iscc packaging\windows\installer.iss /DAppVersion=1.0.0 /DTag=v1.0.0
;
; Per-user install (no admin/UAC needed): PrivilegesRequired=lowest plus the
; {autopf}/{autoprograms} constants below adapt automatically.
;
; Two downloads happen post-install, both best-effort/non-fatal:
;   - Chromium, via the bundled CLI's own --install-chromium flag (see
;     hls_sniffer/cli.py) — same fallback rip() uses lazily on first run if
;     this didn't run or failed, so nothing breaks if it's skipped.
;   - mpv, via Inno's native DownloadTemporaryFile + Windows' built-in
;     tar.exe (bsdtar, ships with Windows 10 1803+/11) to extract the .7z —
;     see InstallMpv() below.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

; The raw git tag that triggered the release build (e.g. "v1.0.0"), used only
; for the output filename below — distinct from AppVersion (which must be a
; plain dotted-numeric string for Windows Installer's version metadata and
; so can't carry the "v" prefix or arbitrary tag text).
#ifndef Tag
  #define Tag AppVersion
#endif

; Pin a known-good mpv build rather than resolving "latest" at install time —
; Inno's Pascal Scripting has no JSON parser, and pinning avoids depending on
; GitHub's API being reachable/well-formed during someone else's install.
; Bump this occasionally: https://github.com/zhongfly/mpv-winbuild/releases
#define MpvReleaseTag "2026-08-26-182fa6ca49"
#define MpvAssetName "mpv-x86_64-20260826-git-182fa6ca49.7z"

[Setup]
AppId={{B14F3769-85E2-4E6B-AB64-EDE10194CA4D}
AppName=hls-sniffer
AppVersion={#AppVersion}
AppPublisher=hls-sniffer contributors
AppPublisherURL=https://github.com/OWNER/hls-sniffer
DefaultDirName={autopf}\hls-sniffer
DefaultGroupName=hls-sniffer
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\..\dist
OutputBaseFilename=hls-sniffer-gui-windows-setup-{#Tag}
Compression=lzma2
SolidCompression=yes
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\hls-sniffer-gui.exe
WizardStyle=modern

[Files]
Source: "..\..\dist\hls-sniffer-gui\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion
Source: "..\..\dist\hls-sniffer.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\hls-sniffer"; Filename: "{app}\hls-sniffer-gui.exe"
Name: "{autodesktop}\hls-sniffer"; Filename: "{app}\hls-sniffer-gui.exe"; Tasks: desktopicon

[Tasks]
Name: desktopicon; Description: "Create a desktop shortcut"; Flags: unchecked

[Run]
Filename: "{app}\hls-sniffer.exe"; Parameters: "--install-chromium"; \
    StatusMsg: "Downloading Chromium (first run only, ~150MB)..."; \
    Flags: runhidden; \
    Description: "chromium"

; mpv isn't a simple single-file [Run] step (needs downloading + extracting
; a 7z), so it's handled in [Code] via CurStepChanged below instead.

[UninstallDelete]
; mpv\ and the install-time logs are created at runtime (not tracked in
; [Files]), so the built-in uninstaller won't remove them on its own.
Type: filesandordirs; Name: "{app}\mpv"
Type: files; Name: "{app}\mpv-download.log"

[Code]
function OnMpvDownloadProgress(const Url, FileName: String; const Progress, ProgressMax: Int64): Boolean;
begin
  Result := True;
end;

procedure LogMpv(const Msg: String);
begin
  SaveStringToFile(ExpandConstant('{app}\mpv-download.log'),
    GetDateTimeString('yyyy-mm-dd hh:nn:ss', #0, #0) + '  ' + Msg + #13#10, True);
end;

procedure InstallMpv();
var
  MpvDir, ArchivePath, ExtractDir, Url: String;
  ResultCode: Integer;
begin
  MpvDir := ExpandConstant('{app}\mpv');
  if FileExists(MpvDir + '\mpv.exe') then
  begin
    LogMpv('mpv.exe already present, skipping.');
    Exit;
  end;

  Url := 'https://github.com/zhongfly/mpv-winbuild/releases/download/{#MpvReleaseTag}/{#MpvAssetName}';
  try
    LogMpv('Downloading ' + Url);
    DownloadTemporaryFile(Url, 'hls-sniffer-mpv.7z', '', @OnMpvDownloadProgress);
  except
    LogMpv('Download failed (non-fatal): ' + GetExceptionMessage);
    Exit;
  end;

  ArchivePath := ExpandConstant('{tmp}\hls-sniffer-mpv.7z');
  ExtractDir := ExpandConstant('{tmp}\hls-sniffer-mpv-extract');
  if not ForceDirectories(ExtractDir) then
  begin
    LogMpv('Could not create extraction folder (non-fatal).');
    Exit;
  end;

  { Windows 10 1803+/11 ship tar.exe (bsdtar/libarchive), which reads .7z
    natively — no extra extraction tool needs to be bundled. }
  if not Exec(ExpandConstant('{sys}\tar.exe'), '-xf "' + ArchivePath + '" -C "' + ExtractDir + '"',
              '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
  begin
    LogMpv('Failed to launch tar.exe (non-fatal).');
    Exit;
  end;
  if ResultCode <> 0 then
  begin
    LogMpv('tar.exe extraction failed with code ' + IntToStr(ResultCode) + ' (non-fatal).');
    Exit;
  end;

  if not ForceDirectories(MpvDir) then
  begin
    LogMpv('Could not create {app}\mpv (non-fatal).');
    Exit;
  end;
  if not CopyFile(ExtractDir + '\mpv.exe', MpvDir + '\mpv.exe', False) then
  begin
    LogMpv('Could not copy mpv.exe into place (non-fatal).');
    Exit;
  end;
  if FileExists(ExtractDir + '\mpv.com') then
    CopyFile(ExtractDir + '\mpv.com', MpvDir + '\mpv.com', False);

  DelTree(ExtractDir, True, True, True);
  DeleteFile(ArchivePath);
  LogMpv('mpv installed successfully at ' + MpvDir + '\mpv.exe');
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    InstallMpv();
end;
