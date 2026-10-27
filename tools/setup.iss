; Установщик «Атласа организма» для Windows (Inno Setup 6.3+).
; Собирается командой  python tools/build_setup.py : она сначала собирает dist/OrganismAtlas (build_exe.py),
; потом вызывает ISCC с версией и путями. Вручную:  iscc tools\setup.iss  (после python tools/build_exe.py)
;
; Ставит программу без прав администратора в %LOCALAPPDATA%\Programs\OrganismAtlas (или, если выбрать
; «для всех пользователей», в Program Files), добавляет ярлыки в меню «Пуск» и на рабочий стол
; и пункт в «Приложения и возможности». При удалении стирает кэш схемы и спрашивает, удалить ли
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
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog commandline
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
ShowLanguageDialog=auto

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
russian.AppName=Атлас организма
english.AppName=Organism Atlas
russian.DeleteUserData=Удалить также настройки и прогресс (историю игр, достижения)?
english.DeleteUserData=Also delete settings and progress (game history, achievements)?

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#Dist}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{cm:AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{cm:AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{cm:AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; кэш готовой схемы (atlas_cache.py) - пересоздаётся сам, хранить незачем
Type: filesandordirs; Name: "{localappdata}\organism_atlas\cache"
Type: dirifempty; Name: "{localappdata}\organism_atlas"

[Code]
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
