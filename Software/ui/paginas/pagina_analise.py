# ui/paginas/pagina_analise.py
"""
Página de Análise (Fase 6).

Cumpre as duas abas que a especificação original previa e que nunca existiram:
"Reconstrução/Comparação" e "Processamento Analítico passo a passo".

Faz quatro coisas sobre coletas já gravadas:

  1. **Carrega várias** — de `data_backup/` ou de qualquer pasta —, mostrando de
     cada uma quantos pontos tem, se é real ou simulada, e se tem metadados.
  2. **Sobrepõe** as curvas, para comparar real com simulado ou uma coleta com
     outra.
  3. **Reprocessa** com a cadeia de incertezas atual, mostrando o pipeline
     passo a passo — o operador vê o número mudar de forma em cada etapa.
  4. **Verifica Stefan-Boltzmann** (A10), um teste independente da física da
     montagem que os CSVs sempre permitiram fazer.
"""
import numpy as np
import pyqtgraph as pg
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFileDialog,
                               QListWidget, QListWidgetItem, QAbstractItemView)
from PySide6.QtCore import Qt

from qfluentwidgets import (HeaderCardWidget, CardWidget, BodyLabel, StrongBodyLabel,
                            CaptionLabel, PushButton, PrimaryPushButton, TextEdit,
                            FluentIcon, InfoBar, InfoBarPosition, SegmentedWidget)

from core import carregador
from utils.error_models import analisar_experimento
from utils.math_models import selecionar_pontos_validos
from utils import stefan_boltzmann


class PaginaAnalise(QWidget):
    """Reprocessamento e comparação de coletas gravadas."""

    def __init__(self, janela, parent=None):
        super().__init__(parent)
        self.setObjectName("pagina_analise")
        self.janela = janela
        self.coletas = []
        self._montar()
        self.atualizar_lista_padrao()

    # -- construção ----------------------------------------------------------

    def _montar(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        layout.addWidget(self._cartao_coletas())

        inferior = QHBoxLayout()
        inferior.addWidget(self._cartao_graficos(), stretch=3)
        inferior.addWidget(self._cartao_relatorio(), stretch=2)
        layout.addLayout(inferior, stretch=1)

    def _cartao_coletas(self) -> HeaderCardWidget:
        cartao = HeaderCardWidget(self)
        cartao.setTitle("Coletas")

        corpo = QWidget()
        vertical = QVBoxLayout(corpo)

        self.lista = QListWidget()
        self.lista.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.lista.setMaximumHeight(150)
        self.lista.itemSelectionChanged.connect(self.ao_selecionar)

        botoes = QHBoxLayout()
        self.btn_recarregar = PushButton(FluentIcon.SYNC, "Recarregar data_backup")
        self.btn_recarregar.clicked.connect(self.atualizar_lista_padrao)
        self.btn_abrir = PushButton(FluentIcon.FOLDER, "Abrir outros arquivos…")
        self.btn_abrir.clicked.connect(self.abrir_arquivos)
        self.btn_analisar = PrimaryPushButton(FluentIcon.VIEW, "Analisar selecionadas")
        self.btn_analisar.clicked.connect(self.analisar)

        botoes.addWidget(self.btn_recarregar)
        botoes.addWidget(self.btn_abrir)
        botoes.addWidget(self.btn_analisar)
        botoes.addStretch()

        self.lbl_resumo = CaptionLabel("")
        self.lbl_resumo.setWordWrap(True)

        vertical.addWidget(self.lista)
        vertical.addLayout(botoes)
        vertical.addWidget(self.lbl_resumo)
        cartao.viewLayout.addWidget(corpo)
        return cartao

    def _cartao_graficos(self) -> CardWidget:
        cartao = CardWidget(self)
        vertical = QVBoxLayout(cartao)
        vertical.setContentsMargins(12, 12, 12, 12)

        self.seletor = SegmentedWidget()
        self.seletor.addItem("bruto", "Fotocorrente × Tensão",
                             lambda: self.desenhar("bruto"))
        self.seletor.addItem("linear", "ln(I) × 1/T",
                             lambda: self.desenhar("linear"))
        self.seletor.addItem("stefan", "log(P) × log(T)",
                             lambda: self.desenhar("stefan"))
        self.seletor.setCurrentItem("bruto")

        pg.setConfigOption('background', '#202020')
        pg.setConfigOption('foreground', '#d4d4d4')
        self.graficos = pg.GraphicsLayoutWidget()
        self.plot = self.graficos.addPlot()
        self.plot.addLegend(offset=(-10, 10))

        vertical.addWidget(self.seletor)
        vertical.addWidget(self.graficos)
        return cartao

    def _cartao_relatorio(self) -> HeaderCardWidget:
        cartao = HeaderCardWidget(self)
        cartao.setTitle("Processamento passo a passo")

        corpo = QWidget()
        vertical = QVBoxLayout(corpo)
        self.relatorio = TextEdit()
        self.relatorio.setReadOnly(True)
        self.relatorio.setStyleSheet(
            "font-family: Consolas, monospace; font-size: 11px;")
        vertical.addWidget(self.relatorio)
        cartao.viewLayout.addWidget(corpo)
        return cartao

    # -- carga ---------------------------------------------------------------

    def atualizar_lista_padrao(self):
        self.carregar(carregador.listar())

    def abrir_arquivos(self):
        caminhos, _ = QFileDialog.getOpenFileNames(
            self, "Escolher coletas", "data_backup", "CSV (*.csv)")
        if caminhos:
            self.carregar(caminhos)

    def carregar(self, caminhos: list):
        self.coletas, problemas = carregador.carregar_varias(caminhos)
        self.lista.clear()
        for coleta in self.coletas:
            item = QListWidgetItem(coleta.descricao())
            item.setData(Qt.UserRole, coleta)
            self.lista.addItem(item)

        sem_meta = sum(1 for c in self.coletas if not c.tem_metadados)
        resumo = f"{len(self.coletas)} coleta(s) carregada(s)."
        if sem_meta:
            resumo += (f" {sem_meta} sem metadados — são anteriores à Fase 4 e "
                       "não registram com que parâmetros foram obtidas; a "
                       "reanálise usa os parâmetros atuais da página Parâmetros.")
        if problemas:
            resumo += "  Problemas: " + " | ".join(problemas[:3])
        self.lbl_resumo.setText(resumo)

    def selecionadas(self) -> list:
        return [item.data(Qt.UserRole) for item in self.lista.selectedItems()]

    def ao_selecionar(self):
        self.desenhar(self.seletor.currentRouteKey() or "bruto")

    # -- gráficos ------------------------------------------------------------

    CORES = [(0, 150, 255), (255, 165, 0), (60, 220, 120), (255, 80, 80),
             (200, 120, 255), (255, 220, 80)]

    def desenhar(self, modo: str):
        self.plot.clear()
        coletas = self.selecionadas()
        if not coletas:
            return

        rotulos = {
            "bruto": ("Tensão (V)", "Fotocorrente (A)"),
            "linear": ("1/T (K⁻¹)", "ln(I)"),
            "stefan": ("log(T)", "log(V·i)"),
        }
        eixo_x, eixo_y = rotulos.get(modo, rotulos["bruto"])
        self.plot.setLabel('bottom', eixo_x)
        self.plot.setLabel('left', eixo_y)

        for indice, coleta in enumerate(coletas):
            cor = self.CORES[indice % len(self.CORES)]
            nome = coleta.nome[-24:] + (" (sim)" if coleta.simulada else "")

            if modo == "bruto":
                x, y = coleta.tensao_fonte, coleta.fotocorrente
            elif modo == "linear":
                validos = selecionar_pontos_validos(coleta.temperatura,
                                                    coleta.fotocorrente, 0.0)
                if not np.any(validos):
                    continue
                x = 1.0 / coleta.temperatura[validos]
                y = np.log(coleta.fotocorrente[validos])
            else:
                validos = (np.isfinite(coleta.temperatura) & (coleta.temperatura > 0)
                           & np.isfinite(coleta.potencia) & (coleta.potencia > 0))
                if not np.any(validos):
                    continue
                x = np.log(coleta.temperatura[validos])
                y = np.log(coleta.potencia[validos])

            self.plot.addItem(pg.ScatterPlotItem(
                x, y, size=6, pen=pg.mkPen(None), brush=pg.mkBrush(*cor, 200),
                name=nome))

    # -- análise -------------------------------------------------------------

    def analisar(self):
        coletas = self.selecionadas()
        if not coletas:
            InfoBar.warning("Nenhuma coleta selecionada",
                            "Escolha ao menos uma na lista acima.",
                            parent=self.window(), position=InfoBarPosition.TOP,
                            duration=4000)
            return

        try:
            parametros = self.janela.pagina_parametros.painel.coletar()
        except ValueError as erro:
            InfoBar.error("Parâmetros inválidos", str(erro), parent=self.window(),
                          position=InfoBarPosition.TOP, duration=8000)
            return

        linhas = []
        for coleta in coletas:
            linhas.extend(self._analisar_uma(coleta, parametros))
            linhas.append("")

        self.relatorio.setPlainText("\n".join(linhas))
        self.desenhar(self.seletor.currentRouteKey() or "bruto")

    def _analisar_uma(self, coleta, parametros_atuais: dict) -> list:
        """Monta o relatório passo a passo de uma coleta."""
        linhas = [
            "=" * 58,
            coleta.nome,
            "=" * 58,
            f"{coleta.n_pontos} pontos · {'simulada' if coleta.simulada else 'real'}"
            f" · formato {coleta.geracao}",
        ]

        # Parâmetros: os da própria coleta, se houver; senão os da tela.
        registrados = coleta.parametros_conhecidos()
        usados = dict(parametros_atuais)
        if registrados.get("r0") is not None:
            usados.update({k: v for k, v in registrados.items() if v is not None})
            linhas.append("Parâmetros: os REGISTRADOS nos metadados da coleta.")
            if registrados.get("perfil_led"):
                linhas.append(f"  LED {registrados['perfil_led']} · "
                              f"filamento {registrados['perfil_filamento']}")
        else:
            linhas.append("Parâmetros: os ATUAIS da página Parâmetros "
                          "(a coleta não registrou os seus).")

        linhas.append(f"  R0 = {usados['r0']:.4f} Ω · α = {usados['alpha']:g} · "
                      f"β = {usados['beta']:g} · λ = {usados['lam']:g} nm")
        linhas.append("")

        # --- pipeline ---
        tensao = coleta.tensao_medida if coleta.tensao_medida is not None else coleta.tensao_fonte
        linhas.append("PASSO 1 — medidas brutas")
        linhas.append(f"  V: {np.nanmin(tensao):.2f} a {np.nanmax(tensao):.2f} V")
        linhas.append(f"  i: {np.nanmin(coleta.corrente):.3f} a {np.nanmax(coleta.corrente):.3f} A")
        linhas.append(f"  I_LED: {np.nanmin(coleta.fotocorrente):.2e} a "
                      f"{np.nanmax(coleta.fotocorrente):.2e} A")

        linhas.append("PASSO 2 — resistência e temperatura")
        linhas.append(f"  R: {np.nanmin(coleta.resistencia):.3f} a "
                      f"{np.nanmax(coleta.resistencia):.3f} Ω")
        linhas.append(f"  T (gravada): {np.nanmin(coleta.temperatura):.0f} a "
                      f"{np.nanmax(coleta.temperatura):.0f} K")

        mascara = selecionar_pontos_validos(coleta.temperatura, coleta.fotocorrente,
                                            usados['t_minima'])
        linhas.append(f"PASSO 3 — seleção (T ≥ {usados['t_minima']:.0f} K e sinal "
                      "acima do piso do DMM)")
        linhas.append(f"  {int(mascara.sum())} de {coleta.n_pontos} pontos entram na regressão")

        try:
            resultado = analisar_experimento(
                tensao, coleta.corrente, coleta.fotocorrente,
                r0=usados['r0'], alpha=usados['alpha'], beta=usados['beta'],
                lambda_nm=usados['lam'], delta_lambda_nm=usados['delta_lam'],
                r_cabos=usados.get('r_cabos', 0.0) or 0.0,
                u_r0=usados.get('u_r0', 0.0) or 0.0,
                u_fotocorrente_tipo_a=coleta.desvio_fotocorrente,
                t_minima=usados['t_minima'])
        except ValueError as erro:
            linhas.append(f"  ✖ não foi possível analisar: {erro}")
            return linhas

        linhas.append("PASSO 4 — linearização e ajuste ponderado")
        linhas.append(f"  inclinação m = {resultado.ajuste.m:.1f} ± {resultado.ajuste.u_m:.1f}")
        linhas.append(f"  R² = {resultado.ajuste.r2:.4f} · χ²_red = "
                      f"{resultado.ajuste.chi2_reduzido:.3f} · "
                      f"{resultado.ajuste.iteracoes} iterações")

        linhas.append("PASSO 5 — h = −m·λ·k_B/c")
        linhas.append(f"  h = {resultado.texto}")
        linhas.append(f"  erro vs CODATA: {resultado.erro_relativo:.2f}%  "
                      f"({'DENTRO' if resultado.compativel_com_codata else 'FORA'} da incerteza)")
        linhas.append("  orçamento: " + " · ".join(
            f"{nome} {pct:.0f}%" for nome, pct in resultado.orcamento_ordenado()))
        linhas.append(f"  (sem ponderar daria {resultado.h_nao_ponderado:.4e})")

        # --- Stefan-Boltzmann (A10) ---
        linhas.append("")
        linhas.append("VERIFICAÇÃO INDEPENDENTE — lei de Stefan-Boltzmann")
        try:
            sb = stefan_boltzmann.verificar(
                coleta.temperatura, coleta.potencia, usados['t_minima'],
                tensao=tensao, corrente=coleta.corrente)
            linhas.append(f"  log(V·i) × log(T) em {sb.n_pontos} pontos")
            linhas.append(f"  {sb.veredicto}")
            linhas.append(f"  R² = {sb.r2:.4f}")
        except ValueError as erro:
            linhas.append(f"  não aplicável: {erro}")

        return linhas
