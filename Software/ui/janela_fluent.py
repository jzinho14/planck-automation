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
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFrame,
                               QApplication)
from PySide6.QtGui import QCloseEvent
from PySide6.QtCore import Qt, QEvent, QTimer

from qfluentwidgets import (FluentWindow, FluentIcon, NavigationItemPosition,
                            CaptionLabel, ScrollArea, TransparentToolButton)

from core.hardware_manager import HardwareManager
from ui import paleta
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

    def repintar_tema(self):
        self.painel.repintar_tema()


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
        # O tema vem ANTES de qualquer widget: os cartões e os gráficos leem a
        # paleta ao nascer, e repintá-los depois seria trabalho perdido.
        paleta.aplicar_tema()

        self.setWindowTitle("Planck Automation — Constante de Planck por radiação de corpo negro")

        self.hw_manager = HardwareManager()

        self._montar_cabecalho()
        self._montar_area_central()
        self._montar_paginas()

        self.atualizar_cabecalho()

        # A geometria vem POR ÚLTIMO, e a ordem não é detalhe: dimensionar
        # antes de montar as páginas não adianta, porque o layout recalcula ao
        # receber os widgets e estica a janela até o sizeHint do conteúdo — que
        # aqui chega a 1055 px de altura, mais que muitas telas.
        self._ajustar_geometria()

    # -- geometria -----------------------------------------------------------

    LARGURA_DESEJADA = 1280
    ALTURA_DESEJADA = 820
    FRACAO_MAXIMA = 0.92     # da área útil, deixando respiro para a barra de tarefas

    def _ajustar_geometria(self):
        """
        Dimensiona e CENTRALIZA a janela na área útil da tela.

        Numa janela sem moldura isto não é cosmético: quem arrasta a janela é a
        barra de título desenhada por nós. Se ela nascer fora da tela, o
        operador não tem como trazer a janela de volta — nem pela borda, que
        também não existe. Já aconteceu: a janela abriu com só o canto inferior
        esquerdo visível e ficou impossível de usar.

        Por isso a posição é calculada explicitamente em vez de deixada ao
        gerenciador de janelas, e o tamanho é limitado à área disponível.
        """
        tela = QApplication.primaryScreen()
        if tela is None:
            self.resize(self.LARGURA_DESEJADA, self.ALTURA_DESEJADA)
            return

        disponivel = tela.availableGeometry()
        largura = min(self.LARGURA_DESEJADA,
                      int(disponivel.width() * self.FRACAO_MAXIMA))
        altura = min(self.ALTURA_DESEJADA,
                     int(disponivel.height() * self.FRACAO_MAXIMA))

        # Mínimo que ainda deixa a interface utilizável, sem passar da tela.
        self.setMinimumSize(min(940, largura), min(620, altura))

        # setGeometry num golpe só: tamanho e posição juntos, centrados na área
        # útil. Usar resize() e move() separados deixa uma janela intermediária
        # com o tamanho novo na posição velha, que pode cair fora da tela.
        self.setGeometry(
            disponivel.x() + max(0, (disponivel.width() - largura) // 2),
            disponivel.y() + max(0, (disponivel.height() - altura) // 2),
            largura, altura)

    def _dentro_da_tela(self) -> bool:
        """
        A BARRA DE TÍTULO está visível em alguma tela?

        O critério não é "quanto da janela aparece", e sim se o canto superior
        esquerdo está na área útil. Numa janela sem moldura, a barra de título
        é o único lugar por onde se arrasta: com ela fora da tela, a janela
        pode estar 80% visível e ainda assim ser impossível de mover.
        """
        canto = self.frameGeometry().topLeft()
        return any(tela.availableGeometry().contains(canto)
                   for tela in QApplication.screens())

    def mostrar(self):
        """
        Abre maximizada, ocupando a área útil da tela.

        É o modo mais seguro para esta janela: sem moldura, ela depende da
        própria barra de título para ser movida, e maximizada essa barra está
        sempre visível.

        A dança de três passos abaixo não é firula. Geometria aplicada ANTES do
        primeiro `show()` é descartada — o layout recalcula ao receber os
        widgets e estica a janela até o `sizeHint` do conteúdo, que aqui passa
        de 1100 px de altura. Então: mostra-se primeiro, fixa-se a geometria
        (que agora gruda) e só então maximiza. O valor fixado no meio é o que o
        Qt guarda como tamanho de restauração, e é por isso que o botão de
        restaurar devolve uma janela centrada e utilizável.
        """
        self.show()
        self._ajustar_geometria()
        self.showMaximized()

    def showEvent(self, evento):
        """Rede de segurança: se a janela nasceu fora da tela, traz de volta."""
        super().showEvent(evento)
        if not self.isMaximized() and not self._dentro_da_tela():
            self._ajustar_geometria()

    def changeEvent(self, evento):
        """
        Ao sair do modo maximizado, reenquadra a janela.

        O tamanho de restauração que o Qt guarda vem do `sizeHint` do conteúdo,
        que aqui passa de 1100 px de altura — maior que muitas telas. Sem este
        reenquadramento, clicar em "restaurar" devolveria exatamente a janela
        inutilizável que motivou toda esta seção.

        O reajuste é adiado com um disparo de tempo zero porque, durante o
        evento, o Qt ainda está aplicando a geometria antiga.
        """
        super().changeEvent(evento)
        if evento.type() == QEvent.WindowStateChange and not self.isMaximized():
            QTimer.singleShot(0, self._reenquadrar_se_preciso)

    def _reenquadrar_se_preciso(self):
        if self.isMaximized() or self.isMinimized():
            return
        tela = QApplication.primaryScreen()
        if tela is None:
            return
        disponivel = tela.availableGeometry()
        moldura = self.frameGeometry()
        cabe = (moldura.width() <= disponivel.width()
                and moldura.height() <= disponivel.height())
        if not cabe or not self._dentro_da_tela():
            self._ajustar_geometria()

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

        # O alternador de tema mora aqui pela mesma razão que o estado dos
        # instrumentos: vale para a janela inteira, não para uma página. E fica
        # à mão porque a escolha entre claro e escuro depende da sala — a mesma
        # pessoa troca ao sair do laboratório para a aula.
        self.btn_tema = TransparentToolButton(FluentIcon.CONSTRACT)
        self.btn_tema.setFixedSize(38, 30)
        self.btn_tema.clicked.connect(self.alternar_tema)

        barra = self.titleBar.hBoxLayout
        # Os botões de janela são o último item; entramos antes deles.
        posicao = barra.count() - 1
        barra.insertStretch(posicao, 1)
        barra.insertWidget(posicao + 1, self.lbl_estado, 0, Qt.AlignVCenter)
        barra.insertSpacing(posicao + 2, 12)
        barra.insertWidget(posicao + 3, self.btn_tema, 0, Qt.AlignVCenter)
        barra.insertSpacing(posicao + 4, 8)
        self._atualizar_dica_tema()

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

    # -- tema ----------------------------------------------------------------

    def _atualizar_dica_tema(self):
        proximo = "escuro" if not paleta.escuro() else "claro"
        self.btn_tema.setToolTip(f"Mudar para o tema {proximo}")

    def aplicar_tema(self, nome: str):
        """
        Aplica um tema e manda cada página se repintar.

        A biblioteca Fluent redesenha sozinha os widgets dela, mas não sabe
        nada do que foi pintado à mão: gráficos do pyqtgraph, cartões de
        resultado, painéis de registro. Cada página que pinta algo expõe um
        `repintar_tema`, e é ele que fecha essa lacuna.
        """
        paleta.aplicar_tema(nome)
        self._atualizar_dica_tema()
        for pagina in (self.pagina_simulacao, self.pagina_bancada,
                       self.pagina_analise, self.pagina_parametros,
                       self.pagina_conexao):
            repintar = getattr(pagina, "repintar_tema", None)
            if callable(repintar):
                repintar()

    def alternar_tema(self):
        """Troca claro ↔ escuro — o que o botão da barra de título faz."""
        self.aplicar_tema("claro" if paleta.escuro() else "escuro")

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
