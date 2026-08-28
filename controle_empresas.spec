# -*- mode: python ; coding: utf-8 -*-
#
# Receita do PyInstaller pra gerar UM executável ("onefile") do app.
#
#   Windows:   pyinstaller controle_empresas.spec      -> dist\ControleEmpresas.exe
#   Linux:     pyinstaller controle_empresas.spec      -> dist/ControleEmpresas
#
# O PyInstaller NÃO faz cross-compile: pra ter um .exe de Windows é preciso
# rodar este comando dentro do Windows (ou numa VM/CI Windows).
#
# O que este spec cuida:
#   - datas=[('assets', 'assets')]  -> embute as logos das empresas no pacote;
#     em tempo de execução elas aparecem em sys._MEIPASS/assets, e
#     resource_path() (em controle_empresas.py) já sabe achar lá.
#   - console=False  -> app de janela, sem terminal preto atrás.
#   - config.json e o cache NÃO são embutidos: ficam em pastas graváveis por
#     usuário (%APPDATA% / %LOCALAPPDATA% no Windows), resolvidas em runtime.

a = Analysis(
    ['controle_empresas.py'],
    pathex=[],
    binaries=[],
    datas=[('assets', 'assets')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # corta libs que o app não usa, pra o binário não inchar à toa (só têm
    # efeito se estiverem instaladas na máquina de build):
    excludes=['tkinter', 'PyQt5', 'PySide6', 'pytest', 'numpy', 'pytesseract'],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='ControleEmpresas',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon='assets/app.ico',  # descomente quando tiver um ícone .ico
)
