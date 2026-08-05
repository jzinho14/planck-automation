from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QComboBox, QPushButton, QGroupBox, QCheckBox)
from core.hardware_manager import (HardwareManager, preferencias,
                                   CHAVE_MODO_DEMONSTRACAO,
                                   STRING_RECURSO_PWS, STRING_RECURSO_DMM)

class ConnectionPanel(QWidget):
    def __init__(self, hw_manager: HardwareManager):
        super().__init__()
        self.hw_manager = hw_manager
        self.settings = preferencias()

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

        # Modo demonstração: troca os drivers VISA pela bancada simulada.
        self.chk_demo = QCheckBox("🧪 Modo demonstração — bancada simulada, sem hardware")
        self.chk_demo.setToolTip(
            "Roda o experimento contra um filamento e um LED virtuais, calibrados "
            "com os dados reais de data_backup/. Nenhum comando VISA é enviado."
        )
        self.lbl_demo = QLabel()
        self.lbl_demo.setWordWrap(True)
        self.lbl_demo.setStyleSheet("color: #ffb74d; font-size: 11px;")

        group_layout.addLayout(dmm_layout)
        group_layout.addLayout(pws_layout)
        group_layout.addLayout(btn_layout)
        group_layout.addWidget(self.chk_demo)
        group_layout.addWidget(self.lbl_demo)
        group_box.setLayout(group_layout)
        layout.addWidget(group_box)

    def connect_signals(self):
        self.btn_scan.clicked.connect(self.hw_manager.scan_resources)
        self.btn_validate.clicked.connect(self.trigger_validation)
        self.hw_manager.resources_found.connect(self.update_comboboxes)
        self.hw_manager.validation_result.connect(self.update_status)
        self.chk_demo.toggled.connect(self.alternar_modo_demonstracao)

    def load_preferences(self):
        # Restaura o modo salvo; aplicar_modo_demonstracao já preenche as combos
        # (com os recursos simulados ou com o último par validado de verdade).
        demo = self.settings.value(CHAVE_MODO_DEMONSTRACAO, False, type=bool)
        self.chk_demo.setChecked(demo)
        self.aplicar_modo_demonstracao(demo)

    def alternar_modo_demonstracao(self, ativo: bool):
        self.settings.setValue(CHAVE_MODO_DEMONSTRACAO, ativo)
        self.aplicar_modo_demonstracao(ativo)

    def aplicar_modo_demonstracao(self, ativo: bool):
        """
        Reflete o modo na UI.

        Em demonstração as combos passam a apontar para os recursos simulados;
        ao voltar para o modo real, recarregamos o que estava gravado para o
        operador não sair com uma string DEMO:: colada no campo.
        """
        if ativo:
            self.pws_combo.clear()
            self.pws_combo.addItem("PWS4323 (simulado)", STRING_RECURSO_PWS)
            self.dmm_combo.clear()
            self.dmm_combo.addItem("DMM4050 (simulado)", STRING_RECURSO_DMM)
            self.dmm_status.setText("🟡")
            self.pws_status.setText("🟡")
            self.dmm_status.setToolTip("Instrumento simulado")
            self.pws_status.setToolTip("Instrumento simulado")
            self.lbl_demo.setText(
                "Os dados vêm de um filamento e um LED virtuais — não são medidas. "
                "O filamento simulado usa R0 = 1,2 Ω, α = 5,23e-3, β = 7,0e-7 e "
                "LED de 590 nm: use esses mesmos valores nos parâmetros para que "
                "a temperatura seja recuperada corretamente."
            )
        else:
            self.pws_combo.clear()
            self.dmm_combo.clear()
            self.load_saved_resources()
            self.dmm_status.setText("⚪")
            self.pws_status.setText("⚪")
            self.dmm_status.setToolTip("")
            self.pws_status.setToolTip("")
            self.lbl_demo.setText("")

    def load_saved_resources(self):
        """Recoloca nas combos o último par nome/recurso validado."""
        for combo, chave in ((self.dmm_combo, "DMM"), (self.pws_combo, "PWS")):
            nome = self.settings.value(f"Connection/Last{chave}Name", "")
            recurso = self.settings.value(f"Connection/Last{chave}Res", "")
            if nome and recurso and not str(recurso).upper().startswith("DEMO::"):
                combo.addItem(nome, recurso)

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
            recurso = self.get_resource_string(combo)
            status_label.setText("🟡" if str(recurso).upper().startswith("DEMO::") else "🟢")
            status_label.setToolTip(message)
            # Salva o par Nome / Recurso para o próximo uso. Recursos simulados
            # não são gravados: são gerados a partir do modo demonstração, e
            # gravá-los deixaria uma string DEMO:: como "último instrumento
            # válido" para quando o operador voltasse à bancada real.
            if not str(recurso).upper().startswith("DEMO::"):
                self.settings.setValue(f"Connection/Last{device_id}Name", combo.currentText())
                self.settings.setValue(f"Connection/Last{device_id}Res", recurso)
        else:
            status_label.setText("🔴")
            status_label.setToolTip(message)