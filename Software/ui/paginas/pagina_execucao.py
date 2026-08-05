# ui/paginas/pagina_execucao.py
"""
Páginas de execução: Simulação e Bancada (Fase 5).

As duas fazem a mesma coisa — disparar uma coleta, desenhar os gráficos ao
vivo e mostrar o resultado —, mudando só a origem dos dados e os cuidados de
segurança. Por isso partilham uma classe base.

Diferença central em relação à interface antiga: **não há mais sub-abas**. Os
parâmetros vivem na página de Parâmetros, e estas páginas só executam e
mostram. Era o "abas dentro de abas" que tornava a navegação confusa.
"""
import os

import numpy as np
import pyqtgraph as pg
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFileDialog,
                               QMessageBox, QTextEdit)
from PySide6.QtCore import Qt

from qfluentwidgets import (HeaderCardWidget, CardWidget, BodyLabel, TitleLabel,
                            StrongBodyLabel, CaptionLabel, PushButton,
                            PrimaryPushButton, ProgressBar, InfoBar,
                            InfoBarPosition, FluentIcon)

from utils.math_models import selecionar_pontos_validos
from ui.components.indicadores import (Indicador, SeloVeredicto, BarraOrcamento,
                                       LegendaOrcamento, estilo_terminal,
                                       linha_registro, cabecalho_registro)
from ui.components.export_dialog import ExportDialog
from utils.pdf_exporter import generate_planck_report


class PaginaExecucaoBase(QWidget):
    """Esqueleto comum às duas páginas de coleta."""

    titulo = "Execução"
    nome_objeto = "pagina_execucao"
    cor_iniciar = "#2e7d32"

    def __init__(self, janela, parent=None):
        super().__init__(parent)
        self.setObjectName(self.nome_objeto)
        self.janela = janela
        self.worker = None
        self.params = {}
        self.last_results = {}
        self.data_v, self.data_t, self.data_i_led = [], [], []
        self._montar()

    # -- construção ----------------------------------------------------------

    def _montar(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        layout.addWidget(self._cartao_controle())
        layout.addWidget(self._cartao_resultado())
        layout.addWidget(self._cartao_graficos(), stretch=1)

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
        Resultado: número-herói + indicadores + veredicto + orçamento.

        O valor de h é a única coisa que o operador procura ao terminar, então
        ele é o número grande. O resto são diagnósticos — cabem em blocos
        pequenos ao lado, não em frases corridas.
        """
        cartao = HeaderCardWidget(self)
        cartao.setTitle("Resultado")

        corpo = QWidget()
        vertical = QVBoxLayout(corpo)
        vertical.setSpacing(12)

        # --- linha 1: o número que importa + o veredicto ---
        linha_topo = QHBoxLayout()
        coluna_h = QVBoxLayout()
        coluna_h.setSpacing(0)
        self.lbl_h = TitleLabel("—")
        self.lbl_unidade = CaptionLabel("constante de Planck (J·s), incerteza expandida k=2")
        coluna_h.addWidget(self.lbl_h)
        coluna_h.addWidget(self.lbl_unidade)

        self.selo = SeloVeredicto()

        linha_topo.addLayout(coluna_h)
        linha_topo.addStretch()
        linha_topo.addWidget(self.selo)
        vertical.addLayout(linha_topo)

        # --- linha 2: indicadores de diagnóstico ---
        self.indicadores = {
            "erro": Indicador("erro vs CODATA", dica="Distância percentual do valor de referência."),
            "r2": Indicador("R²", dica="Quão bem os pontos se ajustam à reta linearizada."),
            "chi2": Indicador("χ² reduzido",
                              dica="Compara a dispersão observada com a incerteza declarada.\n"
                                   "Neste experimento fica abaixo de 1 por construção:\n"
                                   "a especificação de datasheet é um limite de pior caso."),
            "pontos": Indicador("pontos na regressão",
                                dica="Quantos dos pontos coletados entraram na conta."),
        }
        linha_indicadores = QHBoxLayout()
        linha_indicadores.setSpacing(10)
        for indicador in self.indicadores.values():
            linha_indicadores.addWidget(indicador)
        vertical.addLayout(linha_indicadores)

        # --- linha 3: orçamento de incertezas ---
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
        cartao = CardWidget(self)
        layout = QHBoxLayout(cartao)
        layout.setContentsMargins(12, 12, 12, 12)

        pg.setConfigOption('background', '#202020')
        pg.setConfigOption('foreground', '#d4d4d4')
        self.graficos = pg.GraphicsLayoutWidget()

        self.plot_temp = self.graficos.addPlot(title="Temperatura do filamento (K)")
        self.plot_temp.setLabel('left', "T (K)")
        self.plot_temp.setLabel('bottom', "Tensão (V)")
        self.pontos_temp = pg.ScatterPlotItem(size=6, pen=pg.mkPen(None),
                                              brush=pg.mkBrush(255, 165, 0, 200))
        self.plot_temp.addItem(self.pontos_temp)

        self.plot_bruto = self.graficos.addPlot(title="Fotocorrente (A)")
        self.plot_bruto.setLabel('left', "I (A)")
        self.plot_bruto.setLabel('bottom', "Tensão (V)")
        self.pontos_bruto = pg.ScatterPlotItem(size=6, pen=pg.mkPen(None),
                                               brush=pg.mkBrush(0, 150, 255, 200))
        self.plot_bruto.addItem(self.pontos_bruto)

        self.graficos.nextRow()
        self.plot_linear = self.graficos.addPlot(
            title="Linearização ln(I) × 1/T", colspan=2)
        self.plot_linear.setLabel('left', "ln(I)")
        self.plot_linear.setLabel('bottom', "1/T (K⁻¹)")
        self.plot_linear.addLegend(offset=(-10, 10))
        self.pontos_fora = pg.ScatterPlotItem(
            size=6, pen=pg.mkPen(None), brush=pg.mkBrush(120, 120, 120, 150),
            name="Descartado (fora da região de Wien)")
        self.pontos_usados = pg.ScatterPlotItem(
            size=6, pen=pg.mkPen('w'), brush=pg.mkBrush(255, 60, 60, 220),
            name="Usado na regressão")
        self.reta = pg.PlotDataItem(pen=pg.mkPen('w', width=2, style=Qt.DashLine))
        self.plot_linear.addItem(self.pontos_fora)
        self.plot_linear.addItem(self.pontos_usados)
        self.plot_linear.addItem(self.reta)

        layout.addWidget(self.graficos, stretch=3)

        painel_registro = QWidget()
        coluna = QVBoxLayout(painel_registro)
        coluna.setContentsMargins(0, 0, 0, 0)
        coluna.setSpacing(6)
        coluna.addWidget(CaptionLabel("Registro da coleta"))

        self.registro = QTextEdit()
        self.registro.setReadOnly(True)
        self.registro.setMinimumWidth(320)
        self.registro.setStyleSheet(estilo_terminal())
        self.registro.setHtml(cabecalho_registro())
        coluna.addWidget(self.registro)

        layout.addWidget(painel_registro, stretch=1)

        return cartao

    # -- ciclo de coleta -----------------------------------------------------

    def parametros(self) -> dict:
        """Lê a página de Parâmetros — fonte única de configuração."""
        return self.janela.pagina_parametros.painel.coletar()

    def preparar_inicio(self) -> dict:
        self.data_v.clear(); self.data_t.clear(); self.data_i_led.clear()
        for item in (self.pontos_temp, self.pontos_bruto,
                     self.pontos_usados, self.pontos_fora, self.reta):
            item.setData([], [])
        self.registro.clear()
        self.registro.setHtml(cabecalho_registro())

        params = self.parametros()
        vetor = np.arange(params['v_start'],
                          params['v_end'] + params['v_step'], params['v_step'])
        self.barra.setMaximum(max(len(vetor), 1))
        self.barra.setValue(0)
        self.btn_iniciar.setEnabled(False)
        self.btn_parar.setEnabled(True)
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

        self.registro.append(
            linha_registro(tensao, corrente, temperatura, fotocorrente, bool(usados[-1])))
        self.registro.verticalScrollBar().setValue(
            self.registro.verticalScrollBar().maximum())

        self.barra.setValue(len(self.data_v))
        self.lbl_andamento.setText(
            f"ponto {len(self.data_v)}/{self.barra.maximum()} · {temperatura:.0f} K")
        self.janela.atualizar_status(
            f"Coletando: ponto {len(self.data_v)}/{self.barra.maximum()} · "
            f"{temperatura:.0f} K")

    def mostrar_resultado(self, resultado):
        self.btn_iniciar.setEnabled(True)
        self.btn_parar.setEnabled(False)
        self.btn_pdf.setEnabled(True)

        self.lbl_h.setText(resultado.texto)
        self.indicadores["erro"].definir(f"{resultado.erro_relativo:.2f}%")
        self.indicadores["r2"].definir(f"{resultado.ajuste.r2:.4f}")
        self.indicadores["chi2"].definir(f"{resultado.ajuste.chi2_reduzido:.3f}")
        self.indicadores["pontos"].definir(
            f"{resultado.n_usados}/{resultado.n_total}")

        self.selo.definir(
            resultado.compativel_com_codata,
            "Compatível com a CODATA" if resultado.compativel_com_codata
            else "CODATA fora da incerteza — há sistemático não contabilizado")

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
            imagem = "temp_grafico_pagina.png"
            self.graficos.grab().save(imagem)
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
