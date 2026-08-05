# ui/theme.py

DARK_THEME = """
/* --- Estilos Globais da Janela e Fontes --- */
QWidget {
    background-color: #121212;
    color: #E0E0E0;
    font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
    font-size: 13px;
}

/* --- Abas Principais (QTabWidget) --- */
QTabWidget::pane {
    border: 1px solid #333333;
    border-radius: 4px;
    background-color: #181818;
}

QTabBar::tab {
    background: #1E1E1E;
    border: 1px solid #333333;
    padding: 10px 25px;
    margin-right: 2px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    color: #A0A0A0;
}

QTabBar::tab:selected {
    background: #2D2D2D;
    color: #FFFFFF;
    border-top: 3px solid #1565C0; /* Linha de destaque azul na aba ativa */
    font-weight: bold;
}

QTabBar::tab:hover:!selected {
    background: #252525;
}

/* --- Caixas de Agrupamento (QGroupBox) --- */
QGroupBox {
    border: 1px solid #444444;
    border-radius: 6px;
    margin-top: 15px;
    background-color: #1A1A1A;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 15px;
    padding: 0 5px;
    color: #64B5F6; /* Azul claro para os títulos */
    font-weight: bold;
}

/* --- Botões Padrão (QPushButton) --- */
QPushButton {
    background-color: #2D2D2D;
    border: 1px solid #555555;
    border-radius: 5px;
    padding: 8px 16px;
    color: #FFFFFF;
}

QPushButton:hover {
    background-color: #3D3D3D;
    border: 1px solid #64B5F6;
}

QPushButton:pressed {
    background-color: #1565C0;
    border: 1px solid #1565C0;
}

QPushButton:disabled {
    background-color: #121212;
    color: #555555;
    border: 1px solid #222222;
}

/* --- Entradas de Texto e Dropdowns (QLineEdit, QComboBox) --- */
QLineEdit, QComboBox {
    background-color: #1E1E1E;
    border: 1px solid #444444;
    border-radius: 4px;
    padding: 5px 8px;
    color: #FFFFFF;
    selection-background-color: #1565C0;
}

QLineEdit:focus, QComboBox:focus {
    border: 1px solid #64B5F6;
}

QComboBox::drop-down {
    border: none;
    width: 20px;
}

/* --- Barra de Progresso (QProgressBar) --- */
QProgressBar {
    border: 1px solid #444444;
    border-radius: 5px;
    text-align: center;
    background-color: #1A1A1A;
    color: #FFFFFF;
    font-weight: bold;
}

QProgressBar::chunk {
    background-color: #2E7D32; /* Verde suave quando vai preenchendo */
    border-radius: 4px;
}

/* --- Diálogos de Sistema (QMessageBox, QDialog) --- */
QDialog {
    background-color: #181818;
}
"""