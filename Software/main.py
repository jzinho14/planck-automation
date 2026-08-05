# main.py
import sys
from PySide6.QtWidgets import QApplication
from ui.main_window import MainWindow
from ui.theme import DARK_THEME # Importar o nosso novo tema

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Define o motor de renderização base como Fusion (o mais limpo)
    app.setStyle("Fusion") 
    
    # Aplica a nossa Folha de Estilos Global (QSS)
    app.setStyleSheet(DARK_THEME)
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())