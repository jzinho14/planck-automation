# ui/components/indicadores.py
"""
Blocos de apresentação de resultado, reutilizados pelas páginas de coleta.

Três peças, e a razão de cada uma:

**Indicador** — um número com rótulo. Para números-resumo a forma certa não é
um gráfico: é o próprio número, grande, com a unidade e o rótulo ao lado. Um
gráfico de barras com uma barra só não informa nada além do número.

**Selo de veredicto** — estado (bom / atenção) com ÍCONE E TEXTO, nunca cor
sozinha. Quem não distingue vermelho de verde precisa ler o mesmo veredicto.

**Barra de orçamento** — a proporção de cada fonte na incerteza. Cada faixa
carrega seu rótulo em texto, então a identidade nunca depende só da cor.
"""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QSizePolicy
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QColor

from qfluentwidgets import (CardWidget, CaptionLabel, StrongBodyLabel,
                            BodyLabel, isDarkTheme)

# Cores de estado. São reservadas: nunca reaproveitadas para "série 3".
COR_BOM = "#4CAF50"
COR_ATENCAO = "#FFA726"

# Faixas do orçamento de incertezas. Ordem fixa, atribuída por posição e não
# por rodízio, para que a mesma fonte tenha sempre a mesma cor.
CORES_ORCAMENTO = ["#42A5F5", "#AB47BC", "#26A69A", "#EF5350", "#8D6E63"]


class Indicador(CardWidget):
    """Um número de destaque com rótulo — a 'stat tile'."""

    def __init__(self, rotulo: str, valor: str = "—", dica: str = "", parent=None):
        super().__init__(parent)
        self.setMinimumWidth(120)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

        coluna = QVBoxLayout(self)
        coluna.setContentsMargins(14, 10, 14, 10)
        coluna.setSpacing(2)

        self.lbl_valor = StrongBodyLabel(valor)
        self.lbl_rotulo = CaptionLabel(rotulo)
        self.lbl_rotulo.setWordWrap(True)

        coluna.addWidget(self.lbl_valor)
        coluna.addWidget(self.lbl_rotulo)

        if dica:
            self.setToolTip(dica)

    def definir(self, valor: str, dica: str = None):
        self.lbl_valor.setText(valor)
        if dica is not None:
            self.setToolTip(dica)


class SeloVeredicto(CardWidget):
    """
    Estado do resultado, com ícone + texto.

    A cor reforça, mas nunca carrega sozinha a informação.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        linha = QHBoxLayout(self)
        linha.setContentsMargins(14, 8, 14, 8)
        self.lbl = BodyLabel("—")
        self.lbl.setWordWrap(True)
        linha.addWidget(self.lbl)
        self._neutro()

    def _neutro(self):
        self.lbl.setText("Aguardando coleta")
        self.setStyleSheet("")

    def definir(self, bom: bool, texto: str):
        icone = "✓" if bom else "⚠"
        cor = COR_BOM if bom else COR_ATENCAO
        self.lbl.setText(f"{icone}  {texto}")
        self.setStyleSheet(
            f"SeloVeredicto {{ border-left: 4px solid {cor}; }}")


class BarraOrcamento(QWidget):
    """
    Proporção de cada fonte na incerteza, como faixa horizontal.

    Desenhada à mão porque é uma barra empilhada de uma linha só — não vale
    uma dependência de gráfico. Cada segmento tem 2 px de respiro, para que
    fronteiras entre faixas fiquem legíveis mesmo em cores próximas.
    """

    ALTURA = 10
    RESPIRO = 2

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(self.ALTURA)
        self._fatias = []

    def definir(self, fatias: list):
        """`fatias` é [(nome, percentual), ...] já ordenado."""
        self._fatias = list(fatias)
        self.update()

    def paintEvent(self, evento):
        if not self._fatias:
            return
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.Antialiasing)
        pintor.setPen(Qt.NoPen)

        largura_util = self.width() - self.RESPIRO * (len(self._fatias) - 1)
        x = 0.0
        for indice, (_, percentual) in enumerate(self._fatias):
            largura = largura_util * percentual / 100.0
            pintor.setBrush(QColor(CORES_ORCAMENTO[indice % len(CORES_ORCAMENTO)]))
            pintor.drawRoundedRect(int(x), 0, max(int(largura), 1),
                                   self.ALTURA, 3, 3)
            x += largura + self.RESPIRO
        pintor.end()


class LegendaOrcamento(QWidget):
    """Rótulos do orçamento: marcador colorido + nome + percentual, em texto."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.linha = QHBoxLayout(self)
        self.linha.setContentsMargins(0, 0, 0, 0)
        self.linha.setSpacing(14)
        self.linha.addStretch()

    def definir(self, fatias: list):
        while self.linha.count():
            item = self.linha.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for indice, (nome, percentual) in enumerate(fatias):
            cor = CORES_ORCAMENTO[indice % len(CORES_ORCAMENTO)]
            item = CaptionLabel(f"■ {nome}  {percentual:.0f}%")
            item.setStyleSheet(f"color: {cor};")
            # O texto traz nome E percentual: a cor é reforço, não a informação.
            self.linha.addWidget(item)
        self.linha.addStretch()


def estilo_terminal() -> str:
    """
    Folha de estilo do painel de registro.

    Fonte monoespaçada porque as colunas precisam alinhar, mas sem o verde
    sobre preto de terminal antigo: superfície discreta e tinta legível, do
    mesmo tom do resto da interface.
    """
    if isDarkTheme():
        fundo, tinta, borda = "#1B1B1B", "#D6D6D6", "#2E2E2E"
    else:
        fundo, tinta, borda = "#FAFAFA", "#2B2B2B", "#E0E0E0"
    return (f"QTextEdit {{ background-color: {fundo}; color: {tinta};"
            f" border: 1px solid {borda}; border-radius: 6px;"
            f" padding: 10px; selection-background-color: #1565C0;"
            f" font-family: 'Cascadia Mono', 'Consolas', monospace;"
            f" font-size: 12px; line-height: 150%; }}")


def linha_registro(tensao: float, corrente: float, temperatura: float,
                   fotocorrente: float, usado: bool) -> str:
    """
    Uma linha do registro, em HTML, com as colunas alinhadas.

    Pontos descartados saem esmaecidos e marcados com texto — de novo, a
    distinção não pode depender só da cor.
    """
    tinta = "#D6D6D6" if isDarkTheme() else "#2B2B2B"
    apagado = "#7A7A7A"
    cor = tinta if usado else apagado
    marca = "" if usado else "  ·fora"
    return (f'<span style="color:{cor};">'
            f'{tensao:6.2f} V &nbsp;{corrente:6.3f} A &nbsp;'
            f'{temperatura:7.1f} K &nbsp;{fotocorrente:9.2e} A{marca}'
            f'</span>')


def cabecalho_registro() -> str:
    tinta = "#8A8A8A"
    return (f'<span style="color:{tinta};">'
            f'{"tensão":>8} {"corrente":>9} {"temp.":>9} {"fotocorrente":>13}'
            f'</span>')
