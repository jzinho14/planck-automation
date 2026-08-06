# ui/paginas/paginas_coleta.py
"""As duas páginas concretas de coleta: Simulação e Bancada (Fase 5)."""
from PySide6.QtWidgets import QWidget, QHBoxLayout
from qfluentwidgets import (CardWidget, StrongBodyLabel, CaptionLabel,
                            PushButton, FluentIcon, InfoBar, InfoBarPosition)

from core.hardware_manager import (preferencias, limite_corrente,
                                   CHAVE_MODO_DEMONSTRACAO, CHAVE_LIMITE_CORRENTE,
                                   STRING_RECURSO_PWS, STRING_RECURSO_DMM)
from ui import paleta
from ui.components.indicadores import CartaoMetrica
from ui.paginas.pagina_execucao import PaginaExecucaoBase
from ui.tabs.tab_simulation import SimulationWorker
from ui.tabs.tab_experiment import ExperimentWorker


class PaginaSimulacao(PaginaExecucaoBase):
    """Coleta sintética — não toca em hardware nem grava CSV."""

    nome_objeto = "pagina_simulacao"
    titulo_visao = "Simulação"
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

        self.acompanhar(SimulationWorker(params))
        self.worker.new_data_point.connect(self.novo_ponto)
        self.worker.finished_sim.connect(self.mostrar_resultado)
        self.worker.start()
        self.janela.atualizar_status("Simulação em curso")


class PaginaBancada(PaginaExecucaoBase):
    """Coleta real, com os cuidados de segurança sempre visíveis."""

    nome_objeto = "pagina_bancada"
    titulo_visao = "Bancada"
    texto_iniciar = "Iniciar experimento físico"
    texto_parar = "PARAR e processar"

    def _montar(self):
        # A faixa é CONSTRUÍDA antes de `super()._montar()` e só INSERIDA
        # depois. A montagem da base termina repintando a página inteira, e
        # esse repinte passa pelos widgets da faixa — que precisam já existir.
        faixa = self._faixa_seguranca()
        super()._montar()
        # Aviso de segurança fica no topo, acima dos controles: numa página de
        # bancada, o estado do hardware não pode depender de rolagem.
        self._coluna.insertWidget(0, faixa)

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

        # Só LEITURA: o limite é configuração, e configuração mora em
        # Parâmetros › Bancada. Aqui ele aparece para conferência antes de
        # iniciar, não para ser mexido no calor do momento.
        self.lbl_limite = CaptionLabel("")
        self.lbl_limite.setToolTip(
            "Limite de corrente em vigor. Para alterar, vá em "
            "Parâmetros › Bancada.")

        # Leitura ao vivo do ponto de operação, na cor de cada grandeza. São os
        # mesmos cartões do painel de resultado, em versão compacta — o
        # operador não precisa aprender dois vocabulários visuais.
        self.ind_tensao = CartaoMetrica("tensão", acento="info", compacto=True)
        self.ind_corrente = CartaoMetrica("corrente", acento="temperatura",
                                          compacto=True)
        self.ind_potencia = CartaoMetrica(
            "potência", "potência entregue ao filamento (V × i)",
            acento="fotocorrente", compacto=True)
        for indicador in (self.ind_tensao, self.ind_corrente, self.ind_potencia):
            indicador.setFixedWidth(110)

        # Sem ícone de propósito: o ícone do QFluentWidgets é posicionado pelo
        # padding interno dele, e a folha de estilo própria deste botão
        # (necessária para o vermelho) desloca esse cálculo — o ícone acabava
        # em cima do texto. Botão vermelho com rótulo em caixa alta já comunica.
        self.btn_emergencia = PushButton("PARAR TUDO")
        self.btn_emergencia.setMinimumHeight(38)
        self.btn_emergencia.setMinimumWidth(150)
        self.btn_emergencia.setToolTip(
            "Parada de emergência: zera a tensão e desliga a saída da fonte.")
        self.btn_emergencia.clicked.connect(self.parada_de_emergencia)
        self._pintar_emergencia()

        linha.addWidget(self.lbl_seguranca)
        linha.addWidget(self.lbl_limite)
        linha.addStretch()
        linha.addWidget(self.ind_tensao)
        linha.addWidget(self.ind_corrente)
        linha.addWidget(self.ind_potencia)
        linha.addSpacing(10)
        linha.addWidget(self.btn_emergencia)
        return cartao

    def _pintar_emergencia(self):
        """
        O botão de parada em vermelho sólido, nos dois temas.

        Aqui a cor é intencionalmente a mesma do estado "ruim" da paleta: é o
        único controle da interface que precisa ser achado sem ler.
        """
        base = paleta.cor("ruim")
        self.btn_emergencia.setStyleSheet(
            f"PushButton {{ background-color: {base}; color: white;"
            " font-weight: 600; border: none; border-radius: 6px;"
            " padding: 6px 18px; }"
            f"PushButton:hover {{ background-color:"
            f" {paleta.mesclar('#FFFFFF', base, 0.14)}; }}"
            f"PushButton:pressed {{ background-color:"
            f" {paleta.mesclar('#000000', base, 0.18)}; }}")

    def repintar_tema(self):
        super().repintar_tema()
        self._pintar_emergencia()
        for indicador in (self.ind_tensao, self.ind_corrente, self.ind_potencia):
            indicador.repintar()

    def atualizar_faixa(self):
        cfg = preferencias()
        demo = cfg.value(CHAVE_MODO_DEMONSTRACAO, False, type=bool)
        if demo:
            self.lbl_seguranca.setText("🟡  Demonstração — nenhum hardware acionado")
        else:
            self.lbl_seguranca.setText("🔴  Bancada real — o filamento vai aquecer")

        self.lbl_limite.setText(f"limite de corrente: {limite_corrente():.2f} A")

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

        # B4: o limite vem de Parâmetros › Bancada, junto com o resto da
        # configuração. Se por algum motivo não vier, cai na preferência salva.
        params.setdefault('limite_corrente', limite_corrente())
        self.params = params

        self.acompanhar(ExperimentWorker(params, dmm_res, pws_res, demo))
        self.worker.new_data_point.connect(self.novo_ponto)
        self.worker.finished_exp.connect(self.mostrar_resultado)
        self.worker.error_occurred.connect(self.mostrar_erro)
        self.worker.start()

        self.janela.atualizar_status(
            f"Coleta {'simulada' if demo else 'REAL'} em curso · "
            f"salvando em {self.worker.csv_filename}")
