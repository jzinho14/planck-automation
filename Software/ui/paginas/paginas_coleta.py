# ui/paginas/paginas_coleta.py
"""As duas páginas concretas de coleta: Simulação e Bancada (Fase 5)."""
from PySide6.QtWidgets import QWidget, QHBoxLayout
from qfluentwidgets import (CardWidget, StrongBodyLabel, CaptionLabel,
                            PushButton, FluentIcon, InfoBar, InfoBarPosition)

from core.hardware_manager import (preferencias, limite_corrente,
                                   CHAVE_MODO_DEMONSTRACAO,
                                   STRING_RECURSO_PWS, STRING_RECURSO_DMM)
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
        self.layout().insertWidget(0, self._faixa_seguranca())

    def _faixa_seguranca(self) -> CardWidget:
        cartao = CardWidget(self)
        linha = QHBoxLayout(cartao)
        linha.setContentsMargins(18, 10, 18, 10)

        self.lbl_seguranca = StrongBodyLabel("⚪ Verifique as ligações antes de iniciar")
        self.lbl_limite = CaptionLabel("")

        self.btn_emergencia = PushButton(FluentIcon.CLOSE, "PARADA DE EMERGÊNCIA")
        self.btn_emergencia.setStyleSheet(
            "PushButton { background-color: #8b0000; color: white; font-weight: bold; }")
        self.btn_emergencia.clicked.connect(self.parada_de_emergencia)

        linha.addWidget(self.lbl_seguranca)
        linha.addSpacing(12)
        linha.addWidget(self.lbl_limite)
        linha.addStretch()
        linha.addWidget(self.btn_emergencia)
        return cartao

    def atualizar_faixa(self):
        cfg = preferencias()
        demo = cfg.value(CHAVE_MODO_DEMONSTRACAO, False, type=bool)
        if demo:
            self.lbl_seguranca.setText("🟡 Modo demonstração — nenhum hardware será acionado")
        else:
            self.lbl_seguranca.setText("🔴 Bancada real — o filamento vai aquecer")
        self.lbl_limite.setText(f"limite de corrente: {limite_corrente():.2f} A")

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
