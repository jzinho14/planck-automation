# ui/paginas/pagina_conexao.py
"""
Página de Conexão (Fase 5).

Substitui o painel de ligações antigo e resolve dois bugs que dependiam
justamente de existir onde configurar:

  B4 — o limite de corrente da fonte estava fixo em 2.0 A no código, com um
       comentário ao lado dizendo 1.5 A. Agora é campo, com o valor efetivo
       gravado nos metadados de cada coleta.
  B5 — o endereço do multímetro estava escrito no código. Agora são campos de
       IP e porta, persistidos em QSettings.
"""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFormLayout
from PySide6.QtCore import Qt, Signal

from qfluentwidgets import (HeaderCardWidget, BodyLabel, StrongBodyLabel,
                            LineEdit, EditableComboBox, PushButton, PrimaryPushButton,
                            SwitchButton, DoubleSpinBox, InfoBar, InfoBarPosition,
                            FluentIcon, CaptionLabel)

from core.hardware_manager import (preferencias, CHAVE_MODO_DEMONSTRACAO,
                                   STRING_RECURSO_PWS, STRING_RECURSO_DMM,
                                   CHAVE_IP_DMM, CHAVE_PORTA_DMM,
                                   CHAVE_LIMITE_CORRENTE, IP_DMM_PADRAO,
                                   PORTA_DMM_PADRAO, LIMITE_CORRENTE_PADRAO)
from core.mock_hardware import bancada_simulada
from utils.math_models import TEMPERATURA_AMBIENTE_PADRAO


class PaginaConexao(QWidget):
    """Descoberta, validação e configuração dos instrumentos."""

    estado_mudou = Signal()   # a janela usa para atualizar o cabeçalho

    def __init__(self, hw_manager, parent=None):
        super().__init__(parent)
        self.setObjectName("pagina_conexao")
        self.hw_manager = hw_manager
        self.settings = preferencias()

        self._montar()
        self._ligar_sinais()
        self._carregar_preferencias()

    # -- construção ----------------------------------------------------------

    def _montar(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        layout.addWidget(self._cartao_instrumentos())
        layout.addWidget(self._cartao_seguranca())
        layout.addWidget(self._cartao_demonstracao())
        layout.addStretch()

    def _cartao_instrumentos(self) -> HeaderCardWidget:
        cartao = HeaderCardWidget(self)
        cartao.setTitle("Instrumentos")

        corpo = QWidget()
        forma = QFormLayout(corpo)

        # EditableComboBox: o operador precisa poder digitar um endereço que
        # a varredura não encontrou.
        self.combo_pws = EditableComboBox()
        self.combo_pws.setMinimumWidth(360)

        self.combo_dmm = EditableComboBox()
        self.combo_dmm.setMinimumWidth(360)

        self.lbl_estado_pws = BodyLabel("⚪ não verificado")
        self.lbl_estado_dmm = BodyLabel("⚪ não verificado")

        # B5: endereço do multímetro deixa de ser constante no código.
        self.input_ip = LineEdit()
        self.input_ip.setPlaceholderText(IP_DMM_PADRAO)
        self.input_ip.setMaximumWidth(180)
        self.input_porta = LineEdit()
        self.input_porta.setPlaceholderText(PORTA_DMM_PADRAO)
        self.input_porta.setMaximumWidth(100)

        linha_rede = QWidget()
        h = QHBoxLayout(linha_rede)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(self.input_ip)
        h.addWidget(BodyLabel(":"))
        h.addWidget(self.input_porta)
        h.addStretch()

        self.btn_scan = PushButton(FluentIcon.SEARCH, "Procurar instrumentos")
        self.btn_validar = PrimaryPushButton(FluentIcon.ACCEPT, "Verificar ligações")

        linha_botoes = QWidget()
        hb = QHBoxLayout(linha_botoes)
        hb.setContentsMargins(0, 0, 0, 0)
        hb.addWidget(self.btn_scan)
        hb.addWidget(self.btn_validar)
        hb.addStretch()

        forma.addRow(StrongBodyLabel("Fonte PWS4323 (USB):"), self.combo_pws)
        forma.addRow("", self.lbl_estado_pws)
        forma.addRow(StrongBodyLabel("Multímetro DMM4050 (rede):"), self.combo_dmm)
        forma.addRow("", self.lbl_estado_dmm)
        forma.addRow(StrongBodyLabel("Endereço do multímetro:"), linha_rede)
        forma.addRow("", CaptionLabel(
            "Se o aparelho mudar de IP, corrija aqui e procure de novo — "
            "o endereço fica guardado para as próximas sessões."))
        forma.addRow("", linha_botoes)

        cartao.viewLayout.addWidget(corpo)
        return cartao

    def _cartao_seguranca(self) -> HeaderCardWidget:
        cartao = HeaderCardWidget(self)
        cartao.setTitle("Segurança da bancada")

        corpo = QWidget()
        forma = QFormLayout(corpo)

        # B4: limite de corrente configurável, com faixa restrita ao que a
        # fonte entrega (0–3 A) e passo fino.
        self.spin_limite = DoubleSpinBox()
        self.spin_limite.setRange(0.1, 3.0)
        self.spin_limite.setSingleStep(0.1)
        self.spin_limite.setDecimals(2)
        self.spin_limite.setSuffix(" A")
        self.spin_limite.setMaximumWidth(160)

        forma.addRow(StrongBodyLabel("Limite de corrente da fonte:"), self.spin_limite)
        forma.addRow("", CaptionLabel(
            "É a proteção do filamento: a fonte não entrega mais que isto, "
            "entrando em modo corrente constante. O valor usado fica gravado "
            "nos metadados de cada coleta."))

        cartao.viewLayout.addWidget(corpo)
        return cartao

    def _cartao_demonstracao(self) -> HeaderCardWidget:
        cartao = HeaderCardWidget(self)
        cartao.setTitle("Modo demonstração")

        corpo = QWidget()
        vertical = QVBoxLayout(corpo)

        linha = QWidget()
        h = QHBoxLayout(linha)
        h.setContentsMargins(0, 0, 0, 0)
        self.switch_demo = SwitchButton()
        self.switch_demo.setOnText("Ligado")
        self.switch_demo.setOffText("Desligado")
        h.addWidget(BodyLabel("Rodar com bancada simulada, sem hardware"))
        h.addWidget(self.switch_demo)
        h.addStretch()

        self.lbl_demo = CaptionLabel()
        self.lbl_demo.setWordWrap(True)

        vertical.addWidget(linha)
        vertical.addWidget(self.lbl_demo)
        cartao.viewLayout.addWidget(corpo)
        return cartao

    # -- comportamento -------------------------------------------------------

    def _ligar_sinais(self):
        self.btn_scan.clicked.connect(self.hw_manager.scan_resources)
        self.btn_validar.clicked.connect(self.validar)
        self.hw_manager.resources_found.connect(self.preencher_combos)
        self.hw_manager.validation_result.connect(self.mostrar_validacao)
        self.switch_demo.checkedChanged.connect(self.alternar_demonstracao)
        self.input_ip.editingFinished.connect(self.gravar_endereco_dmm)
        self.input_porta.editingFinished.connect(self.gravar_endereco_dmm)
        self.spin_limite.valueChanged.connect(self.gravar_limite_corrente)

    def _carregar_preferencias(self):
        self.input_ip.setText(self.settings.value(CHAVE_IP_DMM, IP_DMM_PADRAO))
        self.input_porta.setText(self.settings.value(CHAVE_PORTA_DMM, PORTA_DMM_PADRAO))
        self.spin_limite.setValue(
            float(self.settings.value(CHAVE_LIMITE_CORRENTE, LIMITE_CORRENTE_PADRAO)))

        demo = self.settings.value(CHAVE_MODO_DEMONSTRACAO, False, type=bool)
        self.switch_demo.setChecked(demo)
        self.aplicar_demonstracao(demo)

    def gravar_endereco_dmm(self):
        ip = self.input_ip.text().strip() or IP_DMM_PADRAO
        porta = self.input_porta.text().strip() or PORTA_DMM_PADRAO
        self.settings.setValue(CHAVE_IP_DMM, ip)
        self.settings.setValue(CHAVE_PORTA_DMM, porta)

    def gravar_limite_corrente(self, valor: float):
        self.settings.setValue(CHAVE_LIMITE_CORRENTE, valor)

    def recurso_de(self, combo) -> str:
        texto = combo.currentText()
        indice = combo.findText(texto)
        if indice != -1 and combo.itemData(indice):
            return combo.itemData(indice)
        return texto

    def preencher_combos(self, itens_pws, itens_dmm):
        for combo, itens in ((self.combo_pws, itens_pws), (self.combo_dmm, itens_dmm)):
            combo.clear()
            for nome, recurso in itens:
                combo.addItem(nome, userData=recurso)

    def validar(self):
        self.lbl_estado_pws.setText("⏳ verificando…")
        self.lbl_estado_dmm.setText("⏳ verificando…")
        self.hw_manager.validate_connection("PWS", self.recurso_de(self.combo_pws))
        self.hw_manager.validate_connection("DMM", self.recurso_de(self.combo_dmm))

    def mostrar_validacao(self, dispositivo: str, valido: bool, mensagem: str):
        rotulo = self.lbl_estado_pws if dispositivo == "PWS" else self.lbl_estado_dmm
        combo = self.combo_pws if dispositivo == "PWS" else self.combo_dmm
        recurso = str(self.recurso_de(combo))
        simulado = recurso.upper().startswith("DEMO::")

        if valido:
            rotulo.setText(("🟡 simulado — " if simulado else "🟢 ") + mensagem.strip()[:60])
            # Recursos simulados nunca viram "último instrumento válido".
            if not simulado:
                self.settings.setValue(f"Connection/Last{dispositivo}Name", combo.currentText())
                self.settings.setValue(f"Connection/Last{dispositivo}Res", recurso)
                InfoBar.success("Ligação válida", f"{dispositivo}: {mensagem.strip()[:70]}",
                                parent=self.window(), position=InfoBarPosition.TOP,
                                duration=3000)
        else:
            rotulo.setText(f"🔴 {mensagem.strip()[:60]}")
            InfoBar.error("Falha na ligação", f"{dispositivo}: {mensagem.strip()[:90]}",
                          parent=self.window(), position=InfoBarPosition.TOP,
                          duration=5000)

        rotulo.setToolTip(mensagem)
        self.estado_mudou.emit()

    def alternar_demonstracao(self, ativo: bool):
        self.settings.setValue(CHAVE_MODO_DEMONSTRACAO, ativo)
        self.aplicar_demonstracao(ativo)
        InfoBar.info(
            "Modo demonstração " + ("ligado" if ativo else "desligado"),
            "Os dados vêm de instrumentos virtuais." if ativo
            else "De volta aos instrumentos reais.",
            parent=self.window(), position=InfoBarPosition.TOP, duration=3000)

    def aplicar_demonstracao(self, ativo: bool):
        if ativo:
            self.preencher_combos([("PWS4323 (simulado)", STRING_RECURSO_PWS)],
                                  [("DMM4050 (simulado)", STRING_RECURSO_DMM)])
            self.lbl_estado_pws.setText("🟡 simulado")
            self.lbl_estado_dmm.setText("🟡 simulado")
            bancada = bancada_simulada()
            r_frio = bancada.resistencia_a_frio(TEMPERATURA_AMBIENTE_PADRAO)
            self.lbl_demo.setText(
                f"Filamento e LED virtuais — não são medidas. Para a temperatura "
                f"ser recuperada corretamente, use em Parâmetros: resistência a "
                f"frio {r_frio:.4f} Ω a {TEMPERATURA_AMBIENTE_PADRAO:.0f} °C, "
                f"α = {bancada.alpha:g}, β = {bancada.beta:g}, "
                f"λ = {bancada.lambda_led * 1e9:.0f} nm.")
        else:
            self.combo_pws.clear()
            self.combo_dmm.clear()
            for combo, chave in ((self.combo_pws, "PWS"), (self.combo_dmm, "DMM")):
                nome = self.settings.value(f"Connection/Last{chave}Name", "")
                recurso = self.settings.value(f"Connection/Last{chave}Res", "")
                if nome and recurso and not str(recurso).upper().startswith("DEMO::"):
                    combo.addItem(nome, userData=recurso)
            self.lbl_estado_pws.setText("⚪ não verificado")
            self.lbl_estado_dmm.setText("⚪ não verificado")
            self.lbl_demo.setText("")

        self.estado_mudou.emit()

    # -- consultado pela janela ---------------------------------------------

    def resumo_estado(self) -> tuple:
        """(texto da fonte, texto do multímetro) para o cabeçalho fixo."""
        return self.lbl_estado_pws.text(), self.lbl_estado_dmm.text()
