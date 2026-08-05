from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                               QComboBox, QPushButton, QGroupBox)
from PySide6.QtCore import QSettings
from core.hardware_manager import HardwareManager

class ConnectionPanel(QWidget):
    def __init__(self, hw_manager: HardwareManager):
        super().__init__()
        self.hw_manager = hw_manager
        self.settings = QSettings("Senac", "PlanckAutomation")
        
        self.setup_ui()
        self.connect_signals()
        self.load_preferences()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        group_box = QGroupBox("Configuração de Instrumentos VISA")
        group_layout = QVBoxLayout()

        # DMM 4050
        dmm_layout = QHBoxLayout()
        self.dmm_status = QLabel("⚪")
        self.dmm_combo = QComboBox()
        self.dmm_combo.setEditable(True)
        self.dmm_combo.setMinimumWidth(350)
        dmm_layout.addWidget(QLabel("DMM 4050 (TCP/IP):"))
        dmm_layout.addWidget(self.dmm_combo)
        dmm_layout.addWidget(self.dmm_status)

        # PWS 4323
        pws_layout = QHBoxLayout()
        self.pws_status = QLabel("⚪")
        self.pws_combo = QComboBox()
        self.pws_combo.setEditable(True)
        self.pws_combo.setMinimumWidth(350)
        pws_layout.addWidget(QLabel("PWS 4323 (USB):"))
        pws_layout.addWidget(self.pws_combo)
        pws_layout.addWidget(self.pws_status)

        # Botões
        btn_layout = QHBoxLayout()
        self.btn_scan = QPushButton("Procurar Instrumentos")
        self.btn_validate = QPushButton("Verificar Ligações")
        btn_layout.addWidget(self.btn_scan)
        btn_layout.addWidget(self.btn_validate)

        group_layout.addLayout(dmm_layout)
        group_layout.addLayout(pws_layout)
        group_layout.addLayout(btn_layout)
        group_box.setLayout(group_layout)
        layout.addWidget(group_box)

    def connect_signals(self):
        self.btn_scan.clicked.connect(self.hw_manager.scan_resources)
        self.btn_validate.clicked.connect(self.trigger_validation)
        self.hw_manager.resources_found.connect(self.update_comboboxes)
        self.hw_manager.validation_result.connect(self.update_status)

    def load_preferences(self):
        last_dmm_name = self.settings.value("Connection/LastDMMName", "")
        last_dmm_res = self.settings.value("Connection/LastDMMRes", "")
        last_pws_name = self.settings.value("Connection/LastPWSName", "")
        last_pws_res = self.settings.value("Connection/LastPWSRes", "")
        
        if last_dmm_name and last_dmm_res:
            self.dmm_combo.addItem(last_dmm_name, last_dmm_res)
        if last_pws_name and last_pws_res:
            self.pws_combo.addItem(last_pws_name, last_pws_res)

    def update_comboboxes(self, pws_items, dmm_items):
        # Limpa e reinsere os itens mantendo o texto amigável visível e a string escondida
        self.pws_combo.clear()
        for name, res in pws_items:
            self.pws_combo.addItem(name, res)

        self.dmm_combo.clear()
        for name, res in dmm_items:
            self.dmm_combo.addItem(name, res)

    def get_resource_string(self, combo: QComboBox) -> str:
        # Pega a string de conexão (oculta) do item selecionado
        current_text = combo.currentText()
        idx = combo.findText(current_text)
        if idx != -1:
            return combo.itemData(idx)
        # Se o usuário digitou manualmente algo diferente na caixa, usa o que ele digitou
        return current_text

    def trigger_validation(self):
        self.dmm_status.setText("⏳")
        self.pws_status.setText("⏳")
        
        dmm_res = self.get_resource_string(self.dmm_combo)
        pws_res = self.get_resource_string(self.pws_combo)
        
        self.hw_manager.validate_connection("DMM", dmm_res)
        self.hw_manager.validate_connection("PWS", pws_res)

    def update_status(self, device_id: str, is_valid: bool, message: str):
        status_label = self.dmm_status if device_id == "DMM" else self.pws_status
        combo = self.dmm_combo if device_id == "DMM" else self.pws_combo
        
        if is_valid:
            status_label.setText("🟢")
            status_label.setToolTip(message)
            # Salva o par Nome / Recurso para o próximo uso
            self.settings.setValue(f"Connection/Last{device_id}Name", combo.currentText())
            self.settings.setValue(f"Connection/Last{device_id}Res", self.get_resource_string(combo))
        else:
            status_label.setText("🔴")
            status_label.setToolTip(message)