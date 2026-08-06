; instalador/planck_setup.iss — instalador do Planck Automation (Fase 7).
;
; Pré-requisito: ter gerado o executável antes —
;     cd Software && .venv\Scripts\pyinstaller planck.spec
; Depois, compilar este script no Inno Setup (ISCC ou a IDE).
; O instalador sai em instalador\Output\.
;
; Decisões, e o porquê de cada uma:
;
; * Instalação POR USUÁRIO ({localappdata}), sem pedir administrador.
;   Os profiles/*.json são feitos para serem editados pelo operador (Fase 4),
;   e os CSVs de coleta nascem na pasta de trabalho — nada disso pode morar
;   em Program Files, que é somente leitura para usuário comum.
;
; * O atalho fixa WorkingDir na pasta do aplicativo: é lá que data_backup\
;   é criado, junto do executável, onde o operador o encontra.
;
; * Docs\ (artigo + datasheets) entra ao lado do exe: é onde
;   content/referencias.py procura as cópias locais quando congelado.
;
; * NI-VISA NÃO vai junto: é instalação da National Instruments, licenciada à
;   parte, e só é necessária para a bancada real — simulação e demonstração
;   funcionam sem ela.
;
; ⚠ GPLv3 (PENDENCIAS.txt, P6): o QFluentWidgets comunitário é GPLv3.
;   Compilar este instalador para USO PRÓPRIO não dispara obrigação nenhuma;
;   distribuir o instalador a terceiros sim. Não repassar sem resolver P6.

#define NomeApp "Planck Automation"
#define Versao "2.0"
#define Editor "Grupo de pesquisa — Constante de Planck"
#define PastaDist "..\Software\dist\PlanckAutomation"

[Setup]
AppId={{3CA91F96-FB9E-4ACE-882E-B00E4392DF42}
AppName={#NomeApp}
AppVersion={#Versao}
AppPublisher={#Editor}
DefaultDirName={localappdata}\PlanckAutomation
DefaultGroupName={#NomeApp}
PrivilegesRequired=lowest
OutputBaseFilename=PlanckAutomation-{#Versao}-instalador
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
; A coleta grava CSV ao lado do exe; desinstalar não pode apagar dados de
; pesquisa silenciosamente. O desinstalador remove só o que instalou.

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Files]
; O aplicativo inteiro, como o PyInstaller o produziu.
Source: "{#PastaDist}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs
; Referências (artigo RBEF + datasheets Tektronix) para a aba Referências.
Source: "..\Docs\*"; DestDir: "{app}\Docs"; Flags: recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#NomeApp}"; Filename: "{app}\PlanckAutomation.exe"; WorkingDir: "{app}"
Name: "{userdesktop}\{#NomeApp}"; Filename: "{app}\PlanckAutomation.exe"; WorkingDir: "{app}"; Tasks: atalhodesktop

[Tasks]
Name: "atalhodesktop"; Description: "Criar atalho na área de trabalho"; Flags: unchecked

[Run]
Filename: "{app}\PlanckAutomation.exe"; Description: "Abrir o {#NomeApp} agora"; Flags: nowait postinstall skipifsilent
