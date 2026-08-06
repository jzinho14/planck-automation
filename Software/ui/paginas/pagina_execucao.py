# ui/paginas/pagina_execucao.py
"""
Páginas de execução: Simulação e Bancada (Fase 5).

As duas fazem a mesma coisa — disparar uma coleta, desenhar os gráficos ao
vivo e mostrar o resultado —, mudando só a origem dos dados e os cuidados de
segurança. Por isso partilham uma classe base.

Diferença central em relação à interface antiga: **não há mais sub-abas**. Os
parâmetros vivem na página de Parâmetros, e estas páginas só executam e
mostram. Era o "abas dentro de abas" que tornava a navegação confusa.

O painel de resultado é um painel de indicadores: o valor de h em corpo grande
e centralizado, e os diagnósticos em cartões coloridos ao lado. Cor com
significado fixo (ver `ui/paleta.py`) e sempre acompanhada de número e texto.
"""
import os

import numpy as np
import pyqtgraph as pg
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFileDialog,
                               QMessageBox, QTextEdit, QFrame, QStackedWidget)
from PySide6.QtCore import Qt

from qfluentwidgets import (HeaderCardWidget, CardWidget, CaptionLabel,
                            PushButton, PrimaryPushButton, ProgressBar, InfoBar,
                            InfoBarPosition, FluentIcon, ScrollArea,
                            SegmentedWidget)

from utils.math_models import selecionar_pontos_validos
from ui import paleta
from ui.components.indicadores import (CartaoMetrica, CartaoDestaque,
                                       BarraOrcamento, LegendaOrcamento,
                                       estilo_terminal, linha_registro,
                                       cabecalho_registro)
from ui.components.export_dialog import ExportDialog
from utils.pdf_exporter import generate_planck_report

# Gráficos que existem, em ordem, com título e eixos. A mesma tabela alimenta a
# pilha da página e a janela de visão completa — assim as duas não divergem.
GRAFICOS = (
    ("temp",   "Temperatura do filamento",   "T (K)",  "Tensão (V)"),
    ("bruto",  "Fotocorrente do LED",        "I (A)",  "Tensão (V)"),
    ("linear", "Linearização ln(I) × 1/T",   "ln(I)",  "1/T (K⁻¹)"),
)


def _tom_do_erro(percentual: float) -> str:
    """
    Cor do cartão de erro contra a CODATA.

    Os cortes são de bom senso experimental, não de norma: até 5 % a montagem
    está fazendo o que promete; até 15 % ainda é um resultado didático
    defensável; acima disso alguma coisa precisa ser investigada. A cor é
    reforço — o número está escrito no mesmo cartão.
    """
    if not np.isfinite(percentual):
        return "descartado"
    if percentual <= 5.0:
        return "bom"
    if percentual <= 15.0:
        return "atencao"
    return "ruim"


def _tom_do_r2(r2: float) -> str:
    if not np.isfinite(r2):
        return "descartado"
    if r2 >= 0.99:
        return "bom"
    if r2 >= 0.95:
        return "atencao"
    return "ruim"


class JanelaGraficos(QWidget):
    """
    Janela separada com os três gráficos e o registro, empilhados.

    Existe para quem quer acompanhar tudo ao mesmo tempo — num segundo monitor,
    por exemplo — sem que a página principal precise espremer três gráficos
    lado a lado. Ela não recalcula nada: apenas espelha os dados da página.
    """

    def __init__(self, titulo: str, parent=None):
        super().__init__(parent)
        self.setWindowFlag(Qt.Window)
        self.setWindowTitle(f"{titulo} — visão completa")
        self.resize(1000, 900)

        layout = QVBoxLayout(self)
        area = ScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.NoFrame)

        conteudo = QWidget()
        coluna = QVBoxLayout(conteudo)
        coluna.setSpacing(10)

        self.plots = {}
        for chave, titulo_grafico, eixo_y, eixo_x in GRAFICOS:
            grafico = pg.PlotWidget(title=titulo_grafico)
            grafico.setLabel('left', eixo_y)
            grafico.setLabel('bottom', eixo_x)
            grafico.setMinimumHeight(260)
            self.plots[chave] = grafico
            coluna.addWidget(grafico)

        self.itens = {
            "temp": pg.ScatterPlotItem(size=7, pen=pg.mkPen(None)),
            "bruto": pg.ScatterPlotItem(size=7, pen=pg.mkPen(None)),
            "fora": pg.ScatterPlotItem(size=7, pen=pg.mkPen(None)),
            "usados": pg.ScatterPlotItem(size=7, pen=pg.mkPen(None)),
            "reta": pg.PlotDataItem(),
        }
        self.plots["temp"].addItem(self.itens["temp"])
        self.plots["bruto"].addItem(self.itens["bruto"])
        for chave in ("fora", "usados", "reta"):
            self.plots["linear"].addItem(self.itens[chave])

        self.lbl_registro = CaptionLabel("Registro da coleta")
        coluna.addWidget(self.lbl_registro)
        self.registro = QTextEdit()
        self.registro.setReadOnly(True)
        self.registro.setMinimumHeight(220)
        coluna.addWidget(self.registro)

        area.setWidget(conteudo)
        layout.addWidget(area)
        self.repintar_tema()

    def repintar_tema(self):
        for chave, titulo, _, _ in GRAFICOS:
            paleta.pintar_grafico(self.plots[chave], titulo)
        for chave, grandeza in (("temp", "temperatura"), ("bruto", "fotocorrente"),
                                ("fora", "descartado"), ("usados", "regressao")):
            self.itens[chave].setBrush(paleta.pincel(grandeza))
        self.itens["reta"].setPen(paleta.caneta_reta())
        self.registro.setStyleSheet(estilo_terminal())

    def sincronizar(self, pagina):
        """Copia o estado atual dos gráficos e do registro da página."""
        for destino, origem in (("temp", pagina.pontos_temp),
                                ("bruto", pagina.pontos_bruto),
                                ("fora", pagina.pontos_fora),
                                ("usados", pagina.pontos_usados)):
            x, y = origem.getData()
            self.itens[destino].setData(x if x is not None else [],
                                        y if y is not None else [])
        x, y = pagina.reta.getData()
        self.itens["reta"].setData(x if x is not None else [],
                                   y if y is not None else [])
        self.registro.setHtml(pagina.registro.toHtml())
        barra = self.registro.verticalScrollBar()
        barra.setValue(barra.maximum())


class PaginaExecucaoBase(QWidget):
    """Esqueleto comum às duas páginas de coleta."""

    titulo = "Execução"
    titulo_visao = "Coleta"
    nome_objeto = "pagina_execucao"

    def __init__(self, janela, parent=None):
        super().__init__(parent)
        self.setObjectName(self.nome_objeto)
        self.janela = janela
        self.worker = None
        self.params = {}
        self.last_results = {}
        self.data_v, self.data_t, self.data_i_led = [], [], []
        self.linhas_registro = []
        self._teve_resultado = False
        self._montar()

    # -- construção ----------------------------------------------------------

    def _montar(self):
        """
        Conteúdo dentro de uma área rolável.

        Esta página é legitimamente alta: faixa de segurança, controles, painel
        de resultado, gráfico e registro. Somando os mínimos, ela pedia mais de
        1000 px de altura — mais que muitas telas. Sem rolagem, a janela era
        forçada a crescer além do monitor e nascia parcialmente fora dele; numa
        janela sem moldura, isso a torna impossível de arrastar de volta. A
        rolagem resolve na origem: a página encolhe até o que couber.
        """
        externo = QVBoxLayout(self)
        externo.setContentsMargins(0, 0, 0, 0)

        area = ScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.NoFrame)
        area.enableTransparentBackground()

        conteudo = QWidget()
        self._coluna = QVBoxLayout(conteudo)
        self._coluna.setSpacing(12)

        self._coluna.addWidget(self._cartao_controle())
        self._coluna.addWidget(self._cartao_resultado())
        self._coluna.addWidget(self._cartao_graficos(), stretch=1)

        area.setWidget(conteudo)
        externo.addWidget(area)

    def _cartao_controle(self) -> CardWidget:
        cartao = CardWidget(self)
        linha = QHBoxLayout(cartao)
        linha.setContentsMargins(18, 14, 18, 14)

        self.btn_iniciar = PrimaryPushButton(FluentIcon.PLAY, self.texto_iniciar)
        self.btn_iniciar.setMinimumHeight(42)
        self.btn_iniciar.clicked.connect(self.iniciar)

        self.btn_parar = PushButton(FluentIcon.CANCEL, self.texto_parar)
        self.btn_parar.setMinimumHeight(42)
        self.btn_parar.setEnabled(False)
        self.btn_parar.clicked.connect(self.parar)

        self.barra = ProgressBar()
        self.barra.setMinimumWidth(240)

        self.lbl_andamento = CaptionLabel("Pronto")

        linha.addWidget(self.btn_iniciar)
        linha.addWidget(self.btn_parar)
        linha.addSpacing(16)
        linha.addWidget(self.barra, stretch=1)
        linha.addWidget(self.lbl_andamento)
        return cartao

    def _cartao_resultado(self) -> HeaderCardWidget:
        """
        Painel de resultado: destaque + cartões de diagnóstico + orçamento.

        A hierarquia é deliberada e tem três degraus. O valor de h ocupa a
        largura toda porque é o que se procura ao terminar. Os quatro
        diagnósticos vêm abaixo, do mesmo tamanho entre si, porque nenhum deles
        é mais importante que os outros. O orçamento de incertezas fecha, como
        um gráfico pequeno: interessa a quem vai discutir o resultado, não a
        quem só quer o número.
        """
        cartao = HeaderCardWidget(self)
        cartao.setTitle("Resultado")

        corpo = QWidget()
        vertical = QVBoxLayout(corpo)
        vertical.setSpacing(14)

        self.destaque = CartaoDestaque()
        vertical.addWidget(self.destaque)

        # Cada cartão nasce com o acento da grandeza a que se refere; os dois
        # primeiros trocam de cor conforme o valor (ver `_tom_do_erro`).
        self.cartoes = {
            "erro": CartaoMetrica(
                "erro vs CODATA", "distância percentual do valor de referência",
                acento="info"),
            "r2": CartaoMetrica(
                "R²", "aderência dos pontos à reta linearizada",
                acento="fotocorrente"),
            "chi2": CartaoMetrica(
                "χ² reduzido", "dispersão observada ÷ incerteza declarada",
                acento="regressao"),
            "pontos": CartaoMetrica(
                "pontos na regressão", "quantos dos coletados entraram na conta",
                acento="temperatura"),
        }
        grade = QHBoxLayout()
        grade.setSpacing(12)
        for indicador in self.cartoes.values():
            grade.addWidget(indicador)
        vertical.addLayout(grade)

        # A ressalva sobre o χ² é longa demais para caber no cartão sem
        # empurrar a altura dos quatro; fica no tooltip, onde quem quiser a
        # explicação vai buscá-la.
        self.cartoes["chi2"].setToolTip(
            "Dispersão observada dividida pela incerteza declarada.\n"
            "Neste experimento fica abaixo de 1 por construção: a\n"
            "especificação de datasheet é um limite de pior caso, não\n"
            "um desvio padrão.")

        self.lbl_titulo_orcamento = CaptionLabel("Composição da incerteza")
        self.barra_orcamento = BarraOrcamento()
        self.legenda_orcamento = LegendaOrcamento()
        vertical.addWidget(self.lbl_titulo_orcamento)
        vertical.addWidget(self.barra_orcamento)
        vertical.addWidget(self.legenda_orcamento)

        self.btn_pdf = PushButton(FluentIcon.DOCUMENT, "Exportar relatório PDF")
        self.btn_pdf.setEnabled(False)
        self.btn_pdf.clicked.connect(self.exportar_pdf)
        vertical.addWidget(self.btn_pdf, alignment=Qt.AlignLeft)

        cartao.viewLayout.addWidget(corpo)
        return cartao

    def _cartao_graficos(self) -> CardWidget:
        """
        UM gráfico por vez, escolhido por segmentos.

        Três gráficos lado a lado num monitor de 1366 px viram três gráficos
        ilegíveis. Com um de cada vez, o que está na tela é grande o bastante
        para se ler. Quem quiser os três juntos usa "Ver tudo", que abre uma
        janela própria — aí sim com espaço para os três empilhados.
        """
        cartao = CardWidget(self)
        layout = QHBoxLayout(cartao)
        layout.setContentsMargins(12, 12, 12, 12)

        coluna_graficos = QVBoxLayout()

        barra = QHBoxLayout()
        # O callback por item do SegmentedWidget só dispara em clique do
        # usuário; trocar por código não o aciona. Por isso a troca de gráfico
        # é ligada ao SINAL currentItemChanged, que vale para os dois casos.
        self._indice_grafico = {chave: indice
                                for indice, (chave, *_) in enumerate(GRAFICOS)}
        self.seletor_grafico = SegmentedWidget()
        for chave, titulo, _, _ in GRAFICOS:
            self.seletor_grafico.addItem(chave, titulo)
        self.seletor_grafico.currentItemChanged.connect(
            lambda chave: self.pilha_graficos.setCurrentIndex(
                self._indice_grafico.get(chave, 0)))

        self.btn_ver_tudo = PushButton(FluentIcon.ZOOM, "Ver tudo")
        self.btn_ver_tudo.setToolTip(
            "Abre uma janela com os três gráficos e o registro empilhados.")
        self.btn_ver_tudo.clicked.connect(self.abrir_visao_completa)

        barra.addWidget(self.seletor_grafico)
        barra.addStretch()
        barra.addWidget(self.btn_ver_tudo)
        coluna_graficos.addLayout(barra)

        self.pilha_graficos = QStackedWidget()
        self.pilha_graficos.setMinimumHeight(380)

        # Sem título dentro do gráfico: a aba selecionada logo acima já diz
        # qual é. Repetir o nome dois centímetros abaixo dele só rouba altura
        # do desenho. Na janela de visão completa é o contrário — lá os três
        # ficam empilhados, e cada um precisa se identificar.
        self.plot_temp = pg.PlotWidget()
        self.plot_temp.setLabel('left', GRAFICOS[0][2])
        self.plot_temp.setLabel('bottom', GRAFICOS[0][3])
        self.pontos_temp = pg.ScatterPlotItem(size=7, pen=pg.mkPen(None))
        self.plot_temp.addItem(self.pontos_temp)

        self.plot_bruto = pg.PlotWidget()
        self.plot_bruto.setLabel('left', GRAFICOS[1][2])
        self.plot_bruto.setLabel('bottom', GRAFICOS[1][3])
        self.pontos_bruto = pg.ScatterPlotItem(size=7, pen=pg.mkPen(None))
        self.plot_bruto.addItem(self.pontos_bruto)

        self.plot_linear = pg.PlotWidget()
        self.plot_linear.setLabel('left', GRAFICOS[2][2])
        self.plot_linear.setLabel('bottom', GRAFICOS[2][3])
        self.plot_linear.addLegend(offset=(-10, 10))
        self.pontos_fora = pg.ScatterPlotItem(
            size=7, pen=pg.mkPen(None), name="Descartado (fora da região de Wien)")
        self.pontos_usados = pg.ScatterPlotItem(
            size=7, pen=pg.mkPen(None), name="Usado na regressão")
        self.reta = pg.PlotDataItem()
        for item in (self.pontos_fora, self.pontos_usados, self.reta):
            self.plot_linear.addItem(item)

        for grafico in (self.plot_temp, self.plot_bruto, self.plot_linear):
            self.pilha_graficos.addWidget(grafico)

        coluna_graficos.addWidget(self.pilha_graficos)
        layout.addLayout(coluna_graficos, stretch=3)

        # A seleção inicial vem DEPOIS da pilha existir. Ligado a
        # `currentItemChanged`, `setCurrentItem` dispara de verdade — inclusive
        # nesta primeira chamada —, e o receptor precisa já estar de pé.
        self.seletor_grafico.setCurrentItem("temp")

        painel_registro = QWidget()
        coluna = QVBoxLayout(painel_registro)
        coluna.setContentsMargins(0, 0, 0, 0)
        coluna.setSpacing(6)
        coluna.addWidget(CaptionLabel("Registro da coleta"))

        self.registro = QTextEdit()
        self.registro.setReadOnly(True)
        self.registro.setMinimumWidth(320)
        self.registro.setMinimumHeight(260)
        coluna.addWidget(self.registro)

        layout.addWidget(painel_registro, stretch=1)

        self.visao_completa = None
        self.repintar_tema()
        return cartao

    # -- tema ----------------------------------------------------------------

    def repintar_tema(self):
        """
        Reaplica as cores a tudo que foi pintado à mão.

        Chamada na construção e a cada alternância de tema. Sem ela, alternar
        para o tema claro deixaria gráficos escuros e um registro preto no meio
        de uma interface branca: o `pg.setConfigOption` só vale para gráficos
        criados depois dele, e o HTML do registro tem as cores embutidas.
        """
        for grafico in (self.plot_temp, self.plot_bruto, self.plot_linear):
            paleta.pintar_grafico(grafico)

        for item, grandeza in ((self.pontos_temp, "temperatura"),
                               (self.pontos_bruto, "fotocorrente"),
                               (self.pontos_fora, "descartado"),
                               (self.pontos_usados, "regressao")):
            item.setBrush(paleta.pincel(grandeza))
        self.reta.setPen(paleta.caneta_reta())

        self.registro.setStyleSheet(estilo_terminal())
        self._redesenhar_registro()

        self.destaque.repintar()
        for indicador in self.cartoes.values():
            indicador.repintar()
        self.barra_orcamento.repintar()
        self.legenda_orcamento.repintar()

        if self.visao_completa is not None:
            self.visao_completa.repintar_tema()
            if self.visao_completa.isVisible():
                self.visao_completa.sincronizar(self)

    def _redesenhar_registro(self):
        """Reescreve o registro inteiro com as cores do tema em vigor."""
        partes = [cabecalho_registro()]
        partes.extend(linha_registro(*dados) for dados in self.linhas_registro)
        self.registro.setHtml("<br>".join(partes))
        self.registro.verticalScrollBar().setValue(
            self.registro.verticalScrollBar().maximum())

    def abrir_visao_completa(self):
        """Janela própria com os três gráficos e o registro empilhados."""
        if self.visao_completa is None:
            self.visao_completa = JanelaGraficos(self.titulo_visao, self)
        self.visao_completa.sincronizar(self)
        self.visao_completa.show()
        self.visao_completa.raise_()
        self.visao_completa.activateWindow()

    # -- ciclo de coleta -----------------------------------------------------

    def parametros(self) -> dict:
        """Lê a página de Parâmetros — fonte única de configuração."""
        return self.janela.pagina_parametros.painel.coletar()

    def preparar_inicio(self) -> dict:
        self.data_v.clear(); self.data_t.clear(); self.data_i_led.clear()
        self.linhas_registro.clear()
        for item in (self.pontos_temp, self.pontos_bruto,
                     self.pontos_usados, self.pontos_fora, self.reta):
            item.setData([], [])
        self._redesenhar_registro()
        self.destaque.limpar()
        for indicador in self.cartoes.values():
            indicador.definir("—")
        self.barra_orcamento.definir([])
        self.legenda_orcamento.definir([])

        params = self.parametros()
        vetor = np.arange(params['v_start'],
                          params['v_end'] + params['v_step'], params['v_step'])
        self.barra.setMaximum(max(len(vetor), 1))
        self.barra.setValue(0)
        self.btn_iniciar.setEnabled(False)
        self.btn_parar.setEnabled(True)
        self._teve_resultado = False
        self.params = params
        return params

    def novo_ponto(self, tensao, corrente, temperatura, fotocorrente):
        self.data_v.append(tensao)
        self.data_t.append(temperatura)
        self.data_i_led.append(fotocorrente)

        self.pontos_temp.setData(self.data_v, self.data_t)
        self.pontos_bruto.setData(self.data_v, self.data_i_led)

        temperaturas = np.array(self.data_t, dtype=float)
        correntes = np.array(self.data_i_led, dtype=float)
        plotavel = (correntes > 1e-12) & np.isfinite(temperaturas) & (temperaturas != 0)
        usados = selecionar_pontos_validos(temperaturas, correntes,
                                           self.params.get('t_minima', 0.0))
        for cena, mascara in ((self.pontos_usados, usados),
                              (self.pontos_fora, plotavel & ~usados)):
            if np.any(mascara):
                cena.setData(1 / temperaturas[mascara], np.log(correntes[mascara]))
            else:
                cena.setData([], [])

        # A linha vai para a lista ANTES de ir para a tela: é a lista que
        # permite reescrever o registro inteiro ao trocar de tema.
        self.linhas_registro.append(
            (tensao, corrente, temperatura, fotocorrente, bool(usados[-1])))
        self.registro.append(linha_registro(*self.linhas_registro[-1]))
        self.registro.verticalScrollBar().setValue(
            self.registro.verticalScrollBar().maximum())

        if self.visao_completa is not None and self.visao_completa.isVisible():
            self.visao_completa.sincronizar(self)

        self.barra.setValue(len(self.data_v))
        self.lbl_andamento.setText(
            f"ponto {len(self.data_v)}/{self.barra.maximum()} · {temperatura:.0f} K")
        self.janela.atualizar_status(
            f"Coletando: ponto {len(self.data_v)}/{self.barra.maximum()} · "
            f"{temperatura:.0f} K")

    def mostrar_resultado(self, resultado):
        self._teve_resultado = True
        self.btn_iniciar.setEnabled(True)
        self.btn_parar.setEnabled(False)
        self.btn_pdf.setEnabled(True)

        self.destaque.definir(resultado)

        self.cartoes["erro"].definir(f"{resultado.erro_relativo:.2f}%",
                                     _tom_do_erro(resultado.erro_relativo))
        self.cartoes["r2"].definir(f"{resultado.ajuste.r2:.4f}",
                                   _tom_do_r2(resultado.ajuste.r2))
        self.cartoes["chi2"].definir(f"{resultado.ajuste.chi2_reduzido:.3f}")
        self.cartoes["pontos"].definir(
            f"{resultado.n_usados}/{resultado.n_total}")

        fatias = resultado.orcamento_ordenado()
        self.barra_orcamento.definir(fatias)
        self.legenda_orcamento.definir(fatias)

        usados = resultado.mascara
        temperaturas = resultado.temperaturas
        if usados is not None and np.any(usados):
            x = 1 / temperaturas[usados]
            extremos = np.array([np.min(x), np.max(x)])
            self.reta.setData(extremos, resultado.ajuste.m * extremos + resultado.ajuste.c)

        self.last_results = {
            'h_ref': 6.62607015e-34, 'h_exp': resultado.h,
            'error': resultado.erro_relativo, 'r2': resultado.ajuste.r2,
            'incerteza_expandida': resultado.incerteza_expandida, 'k': resultado.k,
            'texto': resultado.texto,
            'chi2_reduzido': resultado.ajuste.chi2_reduzido,
            'orcamento': resultado.orcamento_ordenado(),
            'compativel': resultado.compativel_com_codata,
        }

        if self.visao_completa is not None and self.visao_completa.isVisible():
            self.visao_completa.sincronizar(self)

        if resultado.compativel_com_codata:
            InfoBar.success("Coleta concluída",
                            f"h = {resultado.texto} — compatível com a CODATA.",
                            parent=self.window(), position=InfoBarPosition.TOP,
                            duration=6000)
        else:
            InfoBar.warning("Coleta concluída",
                            f"h = {resultado.texto} — a CODATA ficou FORA da "
                            "incerteza; há sistemático não contabilizado.",
                            parent=self.window(), position=InfoBarPosition.TOP,
                            duration=8000)
        self.janela.atualizar_status(f"Concluído · h = {resultado.texto}")

    def mostrar_erro(self, mensagem: str):
        self.btn_iniciar.setEnabled(True)
        self.btn_parar.setEnabled(False)
        InfoBar.error("Erro na coleta", mensagem[:180], parent=self.window(),
                      position=InfoBarPosition.TOP, duration=10000)
        self.janela.atualizar_status("Erro na coleta")

    def acompanhar(self, worker):
        """
        Registra o worker e liga a rede de segurança da interface.

        `finished` do QThread dispara SEMPRE que a thread termina — com
        resultado, com erro ou interrompida. Sem isso, um caminho que não emita
        o sinal de resultado deixa os botões travados e a página presa em
        "encerrando…", que foi exatamente o que aconteceu ao parar uma
        simulação no meio.
        """
        self.worker = worker
        worker.finished.connect(self._ao_encerrar_thread)

    def _ao_encerrar_thread(self):
        self.btn_iniciar.setEnabled(True)
        self.btn_parar.setEnabled(False)
        interrompida = self.lbl_andamento.text() == "encerrando…"
        if interrompida:
            self.lbl_andamento.setText(
                f"interrompida em {len(self.data_v)} ponto(s)")

        # Parar cedo demais deixa poucos pontos na região de Wien, e a análise
        # não roda. Sem este aviso o operador ficaria olhando um painel de
        # resultado vazio sem saber por quê.
        if interrompida and not self._teve_resultado:
            InfoBar.info(
                "Coleta interrompida",
                f"{len(self.data_v)} ponto(s) coletados, mas não há pontos "
                f"suficientes acima de {self.params.get('t_minima', 0):.0f} K "
                "para calcular h. Os dados coletados seguem no gráfico.",
                parent=self.window(), position=InfoBarPosition.TOP, duration=8000)

    def parar(self):
        if self.worker and self.worker.isRunning():
            self.btn_parar.setEnabled(False)
            self.lbl_andamento.setText("encerrando…")
            self.worker.stop()

    # -- relatório -----------------------------------------------------------

    def exportar_pdf(self):
        dialogo = ExportDialog(self)
        if not dialogo.exec():
            return
        caminho, _ = QFileDialog.getSaveFileName(
            self, "Salvar relatório", "Relatorio_Planck.pdf", "PDF (*.pdf)")
        if not caminho:
            return
        try:
            # A linearização é o gráfico do relatório: é dela que sai h. Antes
            # daqui capturava-se um painel com os três gráficos, que deixou de
            # existir quando a página passou a mostrar um de cada vez.
            imagem = "temp_grafico_pagina.png"
            self.plot_linear.grab().save(imagem)
            generate_planck_report(caminho, self.last_results,
                                   self.parametros_formatados(),
                                   dialogo.get_data(), imagem)
            if os.path.exists(imagem):
                os.remove(imagem)
            InfoBar.success("Relatório exportado", caminho, parent=self.window(),
                            position=InfoBarPosition.TOP, duration=5000)
        except Exception as erro:
            QMessageBox.critical(self, "Erro", f"Falha ao gerar PDF:\n{erro}")

    def parametros_formatados(self) -> dict:
        p = self.params
        return {
            'Resistência a frio medida': f"{p.get('r_frio')} Ω a {p.get('t_ambiente')} °C",
            'R0 corrigido (0 °C)': f"{p.get('r0', 0):.4f} Ω",
            'Coef. Linear (α)': f"{p.get('alpha')} K⁻¹",
            'Coef. Quadrático (β)': f"{p.get('beta')} K⁻²",
            'Comprimento de onda (λ)': f"{p.get('lam')} ± {p.get('delta_lam')} nm",
            'Perfis usados': f"{p.get('perfil_led')} / {p.get('perfil_filamento')}",
            'Varredura': f"De {p.get('v_start')} V a {p.get('v_end')} V "
                         f"(passo {p.get('v_step')} V)",
            'Temp. mínima na regressão': f"{p.get('t_minima')} K",
        }
