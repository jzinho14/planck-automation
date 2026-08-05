# ui/janela_fluent.py
"""
Janela principal em Fluent (Fase 5).

Resolve os quatro problemas de navegação apontados na análise da interface
antiga:

  1. **Abas dentro de abas.** Sumiram: os parâmetros têm página própria, e as
     páginas de coleta só executam e mostram.
  2. **Estado do hardware invisível fora da 1ª aba.** Agora há um cabeçalho
     fixo com o estado dos dois instrumentos, visível de qualquer página.
  3. **Parâmetros repetidos entre Simulação e Bancada.** Uma página só, uma
     fonte de configuração — as duas coletas bebem dela.
  4. **Sem retorno do que está acontecendo.** Barra de status permanente com o
     ponto atual, a temperatura e o arquivo em gravação.

A janela antiga continua disponível (ver `main.py`) enquanto a migração é
validada na bancada real.
"""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFrame
from PySide6.QtGui import QCloseEvent
from PySide6.QtCore import Qt

from qfluentwidgets import (FluentWindow, FluentIcon, NavigationItemPosition,
                            BodyLabel, CaptionLabel, StrongBodyLabel,
                            setTheme, Theme, setThemeColor, ScrollArea,
                            HeaderCardWidget)

from core.hardware_manager import HardwareManager
from ui.components.painel_parametros import PainelParametros
from ui.paginas.pagina_conexao import PaginaConexao
from ui.paginas.paginas_coleta import PaginaSimulacao, PaginaBancada
from ui.paginas.pagina_analise import PaginaAnalise
from ui.tabs.tab_references import TabReferences


class PaginaParametros(QWidget):
    """
    A página que centraliza a configuração.

    É o "um único lugar" que faltava: Simulação e Bancada leem daqui, então
    não há como as duas divergirem.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("pagina_parametros")

        layout = QVBoxLayout(self)
        area = ScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.NoFrame)
        area.enableTransparentBackground()

        conteudo = QWidget()
        interno = QVBoxLayout(conteudo)

        cabecalho = CaptionLabel(
            "Estes parâmetros valem para a Simulação E para a Bancada. "
            "Os perfis vêm de arquivos editáveis em Software/profiles/."
        )
        cabecalho.setWordWrap(True)
        interno.addWidget(cabecalho)

        self.painel = PainelParametros(modo="completo")
        interno.addWidget(self.painel)
        interno.addStretch()

        area.setWidget(conteudo)
        layout.addWidget(area)


class PaginaReferencias(QWidget):
    """Envolve a aba de Referências, que já era um QWidget autossuficiente."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("pagina_referencias")
        layout = QVBoxLayout(self)
        self.conteudo = TabReferences()
        layout.addWidget(self.conteudo)


class JanelaPlanck(FluentWindow):
    """Janela principal: navegação lateral, cabeçalho de estado e status."""

    def __init__(self):
        super().__init__()
        setTheme(Theme.DARK)
        setThemeColor("#1565C0")

        self.setWindowTitle("Planck Automation — Constante de Planck por radiação de corpo negro")
        self.resize(1280, 820)

        self.hw_manager = HardwareManager()

        self._montar_cabecalho()
        self._montar_area_central()
        self._montar_paginas()

        self.atualizar_cabecalho()

    # -- estrutura -----------------------------------------------------------

    def _montar_cabecalho(self):
        """
        Estado dos instrumentos na BARRA DE TÍTULO, discreto.

        Ele precisa estar visível de qualquer página, mas é informação de
        canto: quem está olhando um gráfico não quer duas frases de erro VISA
        no meio da tela. Vai como um rótulo curto, com o detalhe no tooltip.

        Cuidado com o layout: `widgetLayout` do FluentWindow é HORIZONTAL
        (navegação | páginas). Inserir um cabeçalho nele cria uma COLUNA, não
        uma faixa — foi exatamente esse o erro da primeira versão, que comeu
        80% da largura da janela.
        """
        self.lbl_estado = CaptionLabel("")
        self.lbl_estado.setObjectName("estadoInstrumentos")

        barra = self.titleBar.hBoxLayout
        # Os botões de janela são o último item; entramos antes deles.
        posicao = barra.count() - 1
        barra.insertStretch(posicao, 1)
        barra.insertWidget(posicao + 1, self.lbl_estado, 0, Qt.AlignVCenter)
        barra.insertSpacing(posicao + 2, 16)

    def _montar_area_central(self):
        """
        Empilha as páginas sobre a barra de status.

        Como `widgetLayout` é horizontal, para ter algo ABAIXO das páginas o
        stackedWidget precisa morar dentro de um container vertical.
        """
        self.barra_status = CaptionLabel("Pronto")
        self.barra_status.setObjectName("barraStatus")
        self.barra_status.setContentsMargins(16, 4, 16, 6)

        self.widgetLayout.removeWidget(self.stackedWidget)

        container = QWidget(self)
        coluna = QVBoxLayout(container)
        coluna.setContentsMargins(0, 0, 0, 0)
        coluna.setSpacing(0)
        coluna.addWidget(self.stackedWidget, stretch=1)
        coluna.addWidget(self.barra_status)

        self.widgetLayout.addWidget(container)

    def _montar_paginas(self):
        self.pagina_conexao = PaginaConexao(self.hw_manager)
        self.pagina_parametros = PaginaParametros()
        self.pagina_simulacao = PaginaSimulacao(self)
        self.pagina_bancada = PaginaBancada(self)
        self.pagina_analise = PaginaAnalise(self)
        self.pagina_referencias = PaginaReferencias()

        self.addSubInterface(self.pagina_conexao, FluentIcon.CONNECT, "Conexão")
        self.addSubInterface(self.pagina_parametros, FluentIcon.SETTING, "Parâmetros")
        self.addSubInterface(self.pagina_simulacao, FluentIcon.DEVELOPER_TOOLS, "Simulação")
        self.addSubInterface(self.pagina_bancada, FluentIcon.IOT, "Bancada")
        self.addSubInterface(self.pagina_analise, FluentIcon.PIE_SINGLE, "Análise")
        self.addSubInterface(self.pagina_referencias, FluentIcon.LIBRARY, "Referências",
                             position=NavigationItemPosition.BOTTOM)

        self.pagina_conexao.estado_mudou.connect(self.atualizar_cabecalho)
        self.stackedWidget.currentChanged.connect(self._ao_trocar_pagina)

    # -- comportamento -------------------------------------------------------

    def _ao_trocar_pagina(self):
        if self.stackedWidget.currentWidget() is self.pagina_bancada:
            self.pagina_bancada.atualizar_faixa()

    def atualizar_cabecalho(self):
        """Resume o estado dos dois instrumentos numa linha curta."""
        fonte, multimetro = self.pagina_conexao.resumo_estado()
        demo = self.pagina_conexao.switch_demo.isChecked()

        partes = [f"{fonte.simbolo} Fonte", f"{multimetro.simbolo} Multímetro"]
        if demo:
            partes.append("🧪 demonstração")
        self.lbl_estado.setText("   ".join(partes))
        self.lbl_estado.setToolTip(
            f"Fonte PWS4323: {fonte.detalhe}\n"
            f"Multímetro DMM4050: {multimetro.detalhe}")

        self.pagina_bancada.atualizar_faixa()

    def atualizar_status(self, texto: str):
        self.barra_status.setText(texto)

    def closeEvent(self, evento: QCloseEvent):
        """Nenhuma coleta pode sobreviver ao fechamento com a fonte ligada."""
        for pagina in (self.pagina_bancada, self.pagina_simulacao):
            worker = getattr(pagina, "worker", None)
            if worker is not None and worker.isRunning():
                worker.stop()
                worker.wait()
        evento.accept()
