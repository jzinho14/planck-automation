# ui/paginas/paginas_coleta.py
"""As duas páginas concretas de coleta: Simulação e Bancada (Fase 5)."""
from PySide6.QtWidgets import QWidget, QHBoxLayout
from qfluentwidgets import (CardWidget, StrongBodyLabel, CaptionLabel,
                            PushButton, FluentIcon, InfoBar, InfoBarPosition,
                            DoubleSpinBox)

from core.hardware_manager import (preferencias, limite_corrente,
                                   CHAVE_MODO_DEMONSTRACAO, CHAVE_LIMITE_CORRENTE,
                                   STRING_RECURSO_PWS, STRING_RECURSO_DMM)
from ui.components.indicadores import Indicador
from ui.paginas.pagina_execucao import PaginaExecucaoBase
from ui.tabs.tab_simulation import SimulationWorker
from ui.tabs.tab_experiment import ExperimentWorker


class PaginaSimulacao(PaginaExecucaoBase):
    """Coleta sintética — não toca em hardware nem grava CSV."""

    nome_objeto = "pagina_simulacao"
    texto_iniciar = "Iniciar coleta simulada"
    texto_parar = "Parar"

    def iniciar(self):
        try:
            params = self.preparar_inicio()
        except ValueError as erro:
            self.btn_iniciar.setEnabled(True)
            self.btn_parar.setEnabled(False)
            InfoBar.error("Parâmetro inválido", str(erro), parent=self.window(),
                          position=InfoBarPosition.TOP, duration=8000)
            return

        self.worker = SimulationWorker(params)
        self.worker.new_data_point.connect(self.novo_ponto)
        self.worker.finished_sim.connect(self.mostrar_resultado)
        self.worker.start()
        self.janela.atualizar_status("Simulação em curso")


class PaginaBancada(PaginaExecucaoBase):
    """Coleta real, com os cuidados de segurança sempre visíveis."""

    nome_objeto = "pagina_bancada"
    texto_iniciar = "Iniciar experimento físico"
    texto_parar = "PARAR e processar"

    def _montar(self):
        super()._montar()
        # Aviso de segurança fica no topo, acima dos controles: numa página de
        # bancada, o estado do hardware não pode depender de rolagem.
        self._coluna.insertWidget(0, self._faixa_seguranca())

    def _faixa_seguranca(self) -> CardWidget:
        """
        Faixa de segurança: estado, limite editável e leitura ao vivo.

        O limite de corrente mora aqui, e não na página de Conexão: é decisão
        de bancada, e o lugar de decidi-la é onde se aperta o botão de iniciar.
        """
        cartao = CardWidget(self)
        linha = QHBoxLayout(cartao)
        linha.setContentsMargins(18, 12, 18, 12)
        linha.setSpacing(14)

        self.lbl_seguranca = StrongBodyLabel("Verifique as ligações antes de iniciar")

        self.spin_limite = DoubleSpinBox()
        self.spin_limite.setRange(0.1, 3.0)
        self.spin_limite.setSingleStep(0.1)
        self.spin_limite.setDecimals(2)
        self.spin_limite.setSuffix(" A")
        self.spin_limite.setFixedWidth(130)
        self.spin_limite.setToolTip(
            "Limite de corrente da fonte — proteção do filamento.\n"
            "A lâmpada em uso opera até 24 W; a 12 V isso dá 2,0 A.\n"
            "O valor fica gravado nos metadados de cada coleta.")
        self.spin_limite.valueChanged.connect(
            lambda v: preferencias().setValue(CHAVE_LIMITE_CORRENTE, v))

        # Leitura ao vivo do ponto de operação.
        self.ind_tensao = Indicador("tensão", "—")
        self.ind_corrente = Indicador("corrente", "—")
        self.ind_potencia = Indicador("potência", "—",
                                      "Potência entregue ao filamento (V × i).")
        for indicador in (self.ind_tensao, self.ind_corrente, self.ind_potencia):
            indicador.setFixedWidth(110)

        self.btn_emergencia = PushButton("PARAR TUDO")
        self.btn_emergencia.setIcon(FluentIcon.CANCEL)
        self.btn_emergencia.setMinimumHeight(38)
        self.btn_emergencia.setMinimumWidth(150)
        self.btn_emergencia.setToolTip(
            "Parada de emergência: zera a tensão e desliga a saída da fonte.")
        self.btn_emergencia.setStyleSheet(
            "PushButton { background-color: #B3261E; color: white;"
            " font-weight: 600; border: none; border-radius: 6px;"
            " padding: 6px 18px; }"
            "PushButton:hover { background-color: #C7372F; }"
            "PushButton:pressed { background-color: #8F1D17; }")
        self.btn_emergencia.clicked.connect(self.parada_de_emergencia)

        linha.addWidget(self.lbl_seguranca)
        linha.addWidget(CaptionLabel("limite:"))
        linha.addWidget(self.spin_limite)
        linha.addStretch()
        linha.addWidget(self.ind_tensao)
        linha.addWidget(self.ind_corrente)
        linha.addWidget(self.ind_potencia)
        linha.addSpacing(10)
        linha.addWidget(self.btn_emergencia)
        return cartao

    def atualizar_faixa(self):
        cfg = preferencias()
        demo = cfg.value(CHAVE_MODO_DEMONSTRACAO, False, type=bool)
        if demo:
            self.lbl_seguranca.setText("🟡  Demonstração — nenhum hardware acionado")
        else:
            self.lbl_seguranca.setText("🔴  Bancada real — o filamento vai aquecer")

        self.spin_limite.blockSignals(True)
        self.spin_limite.setValue(limite_corrente())
        self.spin_limite.blockSignals(False)

    def novo_ponto(self, tensao, corrente, temperatura, fotocorrente):
        """Além de plotar, atualiza a leitura ao vivo do ponto de operação."""
        super().novo_ponto(tensao, corrente, temperatura, fotocorrente)
        potencia = tensao * corrente
        self.ind_tensao.definir(f"{tensao:.2f} V")
        self.ind_corrente.definir(f"{corrente:.3f} A")
        self.ind_potencia.definir(f"{potencia:.2f} W")

    def parada_de_emergencia(self):
        if self.worker and self.worker.isRunning():
            self.parar()
            InfoBar.warning("Parada de emergência",
                            "A fonte está sendo zerada e desligada; os dados "
                            "coletados até aqui já estão no CSV.",
                            parent=self.window(), position=InfoBarPosition.TOP,
                            duration=8000)
        else:
            InfoBar.info("Nada em curso", "Nenhuma coleta está rodando.",
                         parent=self.window(), position=InfoBarPosition.TOP,
                         duration=3000)

    def iniciar(self):
        cfg = preferencias()
        demo = cfg.value(CHAVE_MODO_DEMONSTRACAO, False, type=bool)

        if demo:
            dmm_res, pws_res = STRING_RECURSO_DMM, STRING_RECURSO_PWS
        else:
            dmm_res = cfg.value("Connection/LastDMMRes", "")
            pws_res = cfg.value("Connection/LastPWSRes", "")
            if not dmm_res or not pws_res:
                InfoBar.warning(
                    "Instrumentos não validados",
                    "Vá a Conexão e use 'Verificar ligações' antes de iniciar — "
                    "ou ligue o modo demonstração.",
                    parent=self.window(), position=InfoBarPosition.TOP, duration=8000)
                return

        try:
            params = self.preparar_inicio()
        except ValueError as erro:
            self.btn_iniciar.setEnabled(True)
            self.btn_parar.setEnabled(False)
            InfoBar.error("Parâmetro inválido", str(erro), parent=self.window(),
                          position=InfoBarPosition.TOP, duration=8000)
            return

        # B4: o limite configurado na página de Conexão chega ao worker.
        params['limite_corrente'] = limite_corrente()
        self.params = params

        self.worker = ExperimentWorker(params, dmm_res, pws_res, demo)
        self.worker.new_data_point.connect(self.novo_ponto)
        self.worker.finished_exp.connect(self.mostrar_resultado)
        self.worker.error_occurred.connect(self.mostrar_erro)
        self.worker.start()

        self.janela.atualizar_status(
            f"Coleta {'simulada' if demo else 'REAL'} em curso · "
            f"salvando em {self.worker.csv_filename}")
