; Установщик «Атласа организма» для Windows (Inno Setup 6.3+).
; Собирается командой  python tools/build_setup.py : она сначала собирает dist/OrganismAtlas (build_exe.py),
; потом вызывает ISCC с версией и путями. Вручную:  iscc tools\setup.iss  (после python tools/build_exe.py)
;
; Мастер в два шага: выбор папки (по умолчанию %LOCALAPPDATA%\Programs\OrganismAtlas, прав администратора
; не нужно) и «Готово» с запуском программы. Язык - по языку Windows, без вопросов. Ярлыки в меню «Пуск»
; и на рабочем столе и пункт в «Приложения и возможности» создаются сами. При удалении стирает кэш схемы и спрашивает, удалить ли
; настройки и прогресс (%APPDATA%\organism_atlas).

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#ifndef Dist
  #define Dist SourcePath + "..\dist\OrganismAtlas"
#endif
#ifndef Icon
  #define Icon SourcePath + "..\build\OrganismAtlas.ico"
#endif
#ifndef OutDir
  #define OutDir SourcePath + "..\dist"
#endif
#define AppExe "OrganismAtlas.exe"

[Setup]
; AppId не менять: по нему новая версия ставится поверх старой, а не рядом
AppId={{6F1C2B9E-4D7A-4E5B-9C3F-0A8D2E7B5C41}
AppName={cm:AppName}
AppVersion={#AppVersion}
AppVerName={cm:AppName} {#AppVersion}
AppPublisher=Organism Atlas
DefaultDirName={autopf}\OrganismAtlas
DefaultGroupName={cm:AppName}
DisableProgramGroupPage=yes
DisableDirPage=no
DisableWelcomePage=yes
DisableReadyPage=yes
PrivilegesRequired=lowest
; для всех пользователей - только из командной строки: setup.exe /ALLUSERS. Если выбрать папку, куда нельзя
; писать без прав администратора (Program Files), мастер скажет об этом сразу (NextButtonClick ниже)
PrivilegesRequiredOverridesAllowed=commandline
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#OutDir}
OutputBaseFilename=OrganismAtlas-Setup-{#AppVersion}
SetupIconFile={#Icon}
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={cm:AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
ShowLanguageDialog=no

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
russian.AppName=Атлас организма
english.AppName=Organism Atlas
russian.DeleteUserData=Удалить также настройки и прогресс (историю игр, достижения)?
english.DeleteUserData=Also delete settings and progress (game history, achievements)?
russian.DirNotWritable=В эту папку нельзя установить программу без прав администратора. Выберите другую папку, например предложенную по умолчанию.
english.DirNotWritable=This folder needs administrator rights. Please choose another folder, for example the default one.

[Files]
Source: "{#Dist}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{cm:AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{cm:AppName}"; Filename: "{app}\{#AppExe}"

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{cm:AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; кэш готовой схемы (atlas_cache.py) - пересоздаётся сам, хранить незачем
Type: filesandordirs; Name: "{localappdata}\organism_atlas\cache"
Type: dirifempty; Name: "{localappdata}\organism_atlas"

[Code]
function CanWrite(Dir: String): Boolean;
var
  Created: Boolean;
  Probe: String;
begin
  Created := not DirExists(Dir);
  Result := ForceDirectories(Dir);
  if Result then
  begin
    Probe := AddBackslash(Dir) + '.write-test';
    Result := SaveStringToFile(Probe, '', False);
    DeleteFile(Probe);
  end;
  if Created then
    RemoveDir(Dir);           { пустую папку создаст сама установка; если вернутся и выберут другую - не мусорим }
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (CurPageID = wpSelectDir) and not IsAdminInstallMode and not CanWrite(WizardDirValue) then
  begin
    MsgBox(CustomMessage('DirNotWritable'), mbError, MB_OK);
    Result := False;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Data: String;
begin
  { settings.json и progress.json (settings.py, progress.py); при тихом удалении не трогаем }
  if (CurUninstallStep = usPostUninstall) and not UninstallSilent then
  begin
    Data := ExpandConstant('{userappdata}\organism_atlas');
    if DirExists(Data) and
       (MsgBox(CustomMessage('DeleteUserData'), mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES) then
      DelTree(Data, True, True, True);
  end;
end;
