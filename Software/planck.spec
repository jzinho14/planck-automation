# planck.spec — receita do executável (Fase 7).
#
#     cd Software && .venv\Scripts\pyinstaller planck.spec
#
# Sai em Software/dist/PlanckAutomation/ no modo "onedir": uma pasta com o
# .exe e um _internal/ ao lado. Onedir em vez de onefile de propósito:
#
#   - os profiles/*.json ficam em _internal/profiles/, visíveis e EDITÁVEIS —
#     a modularidade por arquivo (Fase 4) sobrevive ao empacotamento;
#   - o antivírus implica bem menos com onedir do que com onefile;
#   - abre mais rápido (onefile descompacta tudo a cada execução).
#
# O que NÃO vai embutido, e por quê:
#   - Docs/  — os PDFs de referência (25 MB) entram pelo instalador Inno, ao
#     lado do exe; `content/referencias.py` procura lá quando congelado.
#   - data_backup/ — é produzido pelo uso, na pasta de trabalho do atalho.
#
# ⚠ GPLv3: o QFluentWidgets comunitário é GPLv3. Gerar o executável para uso
# próprio (pesquisa/aula) não dispara obrigação nenhuma; DISTRIBUÍ-LO a
# terceiros sim — ver PENDENCIAS.txt, item P6, antes de repassar.

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    # O visa '@ivi' carrega a DLL da NI em tempo de execução via ctypes; o
    # PyInstaller não a vê na análise estática, e não deve embuti-la — ela
    # pertence à instalação do NI-VISA da máquina, como no modo desenvolvimento.
    hiddenimports=['pyvisa.resources.serial'],
    hookspath=[],
    runtime_hooks=[],
    # Cortes de peso: nada disso é usado pelo software.
    excludes=['tkinter', 'matplotlib', 'IPython', 'jedi', 'pytest'],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='PlanckAutomation',
    console=False,            # --windowed: app de bancada, sem terminal atrás
    icon=None,                # sem ícone oficial por enquanto
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name='PlanckAutomation',
)
