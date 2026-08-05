# ui/main_window.py
from PySide6.QtWidgets import QMainWindow, QTabWidget, QVBoxLayout, QWidget
from PySide6.QtGui import QIcon, QCloseEvent

from core.hardware_manager import HardwareManager
from ui.components.connection_panel import ConnectionPanel
from ui.tabs.tab_simulation import TabSimulation
from ui.tabs.tab_experiment import TabExperiment

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Planck Automation v1.0 - Análise Analítica")
        self.resize(1200, 800) # Tamanho base ideal para visualização de dados

        # Instanciar o Gestor de Hardware (O Motor VISA)
        self.hw_manager = HardwareManager()

        self.setup_ui()

    def setup_ui(self):
        # O widget central será um gestor de abas principais
        self.main_tabs = QTabWidget()
        self.main_tabs.setStyleSheet("QTabBar::tab { height: 40px; width: 200px; font-weight: bold; font-size: 14px; }")

        # --- Aba 1: Ligações e Setup ---
        self.tab_setup = QWidget()
        setup_layout = QVBoxLayout(self.tab_setup)
        self.connection_panel = ConnectionPanel(self.hw_manager)
        setup_layout.addWidget(self.connection_panel)
        setup_layout.addStretch() # Empurra o painel para cima

        # --- Aba 2: Simulação Analítica ---
        self.tab_simulation = TabSimulation()

        # --- Aba 3: Experimento Real (O nosso próximo alvo) ---
        self.tab_experiment = TabExperiment(self.hw_manager)

        # Adicionar as abas ao ecrã principal
        self.main_tabs.addTab(self.tab_setup, "🔌 Hardware e Ligações")
        self.main_tabs.addTab(self.tab_simulation, "💻 Simulação")
        self.main_tabs.addTab(self.tab_experiment, "🔬 Experimento Real")

        self.setCentralWidget(self.main_tabs)

    # Adicione este método no final da classe MainWindow
    def closeEvent(self, event: QCloseEvent):
        # Se um experimento estiver a correr, pára-o de imediato
        if hasattr(self, 'tab_experiment') and self.tab_experiment.worker:
            if self.tab_experiment.worker.isRunning():
                self.tab_experiment.worker.stop()
                self.tab_experiment.worker.wait() # Aguarda a fonte desligar em segurança
                
        # Aceita o encerramento da janela
        event.accept()