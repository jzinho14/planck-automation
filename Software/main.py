# main.py
"""
Ponto de entrada do Planck Automation.

A interface Fluent (Fase 5) é a padrão. A janela antiga, de abas, continua
disponível enquanto a nova não for validada com os instrumentos ligados:

    set PLANCK_UI=classica && python main.py

Não é permanente: a janela antiga sai quando a nova tiver rodado um
experimento de verdade na bancada.
"""
import os
import sys

from PySide6.QtWidgets import QApplication

from content.perfis import escrever_padroes_se_ausente


def main() -> int:
    app = QApplication(sys.argv)

    # Materializa profiles/*.json na primeira execução, para o operador poder
    # editá-los. Nunca sobrescreve o que já existe.
    escrever_padroes_se_ausente()

    if os.environ.get("PLANCK_UI", "").lower() == "classica":
        from ui.main_window import MainWindow
        from ui.theme import DARK_THEME
        app.setStyle("Fusion")
        app.setStyleSheet(DARK_THEME)
        janela = MainWindow()
    else:
        from ui.janela_fluent import JanelaPlanck
        janela = JanelaPlanck()

    janela.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
