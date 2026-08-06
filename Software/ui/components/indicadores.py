# ui/components/indicadores.py
"""
Os blocos do painel de resultado — o "dashboard" das páginas de coleta.

Quatro peças, e a razão de cada uma:

**Cartão de destaque** — o valor de h, sozinho, em corpo grande e centralizado.
É a única coisa que o operador procura ao terminar uma coleta; tudo mais na
tela é diagnóstico. A incerteza vem logo abaixo, no mesmo bloco, porque um
valor sem incerteza não é um resultado — é um palpite.

**Cartão de métrica** — um número por cartão, grande e centralizado, com faixa
de cor no topo, rótulo e uma linha explicando o que ele significa. Para
números-resumo a forma certa não é um gráfico: é o próprio número. Um gráfico
de barras com uma barra só não informa nada além do número, e ocupa dez vezes
mais espaço.

**Selo de veredicto** — estado (bom / atenção) com ÍCONE E TEXTO, nunca cor
sozinha. Quem não distingue vermelho de verde precisa ler o mesmo veredicto.

**Barra de orçamento** — a proporção de cada fonte na incerteza. Cada faixa
carrega seu rótulo em texto, então a identidade nunca depende só da cor.

Todos são desenhados à mão sobre `QFrame`, e não sobre o `CardWidget` da
biblioteca, porque precisam de fundo tingido pela cor da grandeza e de faixa de
acento — coisas que o cartão padrão não expõe. Todos têm `repintar()`, chamado
quando o operador alterna entre tema claro e escuro.
"""
from PySide6.QtWidgets import (QWidget, QFrame, QVBoxLayout, QHBoxLayout,
                               QLabel, QSizePolicy)
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QColor, QPainterPath, QPen

from ui import paleta

_SOBRESCRITO = {"0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴",
                "5": "⁵", "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹",
                "-": "⁻", "+": "⁺"}


def sobrescrito(numero: int) -> str:
    """'−34' → '⁻³⁴'. Potência de dez escrita como potência, não como 'e-34'."""
    return "".join(_SOBRESCRITO.get(caractere, caractere) for caractere in str(numero))


def _rotulo(texto: str, tamanho: int, peso: int, cor: str,
            centralizado: bool = True) -> QLabel:
    etiqueta = QLabel(texto)
    if centralizado:
        etiqueta.setAlignment(Qt.AlignCenter)
    etiqueta.setStyleSheet(
        f"color: {cor}; font-size: {tamanho}px; font-weight: {peso};"
        " background: transparent;")
    return etiqueta


class _CartaoPintado(QFrame):
    """
    Base dos cartões: fundo arredondado, borda e faixa de acento no topo.

    A faixa é desenhada dentro do recorte do próprio contorno, e não como um
    retângulo por cima — senão os cantos superiores ficariam quadrados sobre um
    cartão arredondado.
    """

    RAIO = 10
    ALTURA_FAIXA = 4

    def __init__(self, acento: str = "info", parent=None):
        super().__init__(parent)
        self.acento = acento

    def definir_acento(self, acento: str):
        self.acento = acento
        self.repintar()

    def repintar(self):
        """Reaplica as cores do tema em vigor. Sobrescrito pelas subclasses."""
        self.update()

    def paintEvent(self, evento):
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.Antialiasing)

        area = QRectF(self.rect().adjusted(0, 0, -1, -1))
        contorno = QPainterPath()
        contorno.addRoundedRect(area, self.RAIO, self.RAIO)

        pintor.setClipPath(contorno)
        pintor.fillPath(contorno, QColor(paleta.tom_suave(self.acento)))
        pintor.fillRect(0, 0, self.width(), self.ALTURA_FAIXA,
                        QColor(paleta.cor(self.acento)))
        pintor.setClipping(False)

        pintor.setPen(QPen(QColor(paleta.tom_borda(self.acento)), 1))
        pintor.setBrush(Qt.NoBrush)
        pintor.drawPath(contorno)
        pintor.end()


class CartaoMetrica(_CartaoPintado):
    """
    Um número de destaque, centralizado, com rótulo e explicação.

    O acento pode mudar em tempo de execução (`definir` aceita um acento novo):
    é assim que o erro contra a CODATA fica verde quando está pequeno e âmbar
    quando cresce, sem que a cor seja a única pista — o número está ali do lado.
    """

    def __init__(self, rotulo: str, legenda: str = "", acento: str = "info",
                 compacto: bool = False, parent=None):
        super().__init__(acento, parent)
        self.compacto = compacto
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.setMinimumWidth(100 if compacto else 150)

        coluna = QVBoxLayout(self)
        if compacto:
            coluna.setContentsMargins(12, 12, 12, 10)
            coluna.setSpacing(0)
        else:
            coluna.setContentsMargins(16, 18, 16, 16)
            coluna.setSpacing(3)

        self.lbl_valor = _rotulo("—", 19 if compacto else 30, 700, "#000000")
        self.lbl_rotulo = _rotulo(rotulo, 11 if compacto else 12, 600, "#000000")
        self.lbl_legenda = _rotulo(legenda, 11, 400, "#000000")
        self.lbl_legenda.setWordWrap(True)
        self.lbl_legenda.setVisible(bool(legenda) and not compacto)

        coluna.addWidget(self.lbl_valor)
        coluna.addWidget(self.lbl_rotulo)
        coluna.addWidget(self.lbl_legenda)

        if legenda:
            self.setToolTip(legenda)
        self.repintar()

    def definir(self, valor: str, acento: str = None, dica: str = None):
        self.lbl_valor.setText(valor)
        if dica is not None:
            self.setToolTip(dica)
        if acento is not None and acento != self.acento:
            self.acento = acento
        self.repintar()

    def repintar(self):
        self.lbl_valor.setStyleSheet(
            f"color: {paleta.cor(self.acento)};"
            f" font-size: {19 if self.compacto else 30}px; font-weight: 700;"
            " background: transparent;")
        self.lbl_rotulo.setStyleSheet(
            f"color: {paleta.cor('tinta')};"
            f" font-size: {11 if self.compacto else 12}px; font-weight: 600;"
            " background: transparent;")
        self.lbl_legenda.setStyleSheet(
            f"color: {paleta.cor('tinta_fraca')}; font-size: 11px;"
            " background: transparent;")
        self.update()


class SeloVeredicto(QFrame):
    """
    Pastilha de estado: ícone + texto, com fundo tingido.

    A cor reforça, mas nunca carrega sozinha a informação — o texto diz o mesmo
    que a cor, e o ícone diz de novo.
    """

    RAIO = 14

    def __init__(self, parent=None):
        super().__init__(parent)
        self.acento = "descartado"
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)

        linha = QHBoxLayout(self)
        linha.setContentsMargins(16, 7, 16, 7)
        self.lbl = QLabel("Aguardando coleta")
        self.lbl.setAlignment(Qt.AlignCenter)
        linha.addWidget(self.lbl)
        self.repintar()

    def definir(self, bom: bool, texto: str):
        self.acento = "bom" if bom else "atencao"
        self.lbl.setText(f"{'✓' if bom else '⚠'}  {texto}")
        self.repintar()

    def limpar(self):
        self.acento = "descartado"
        self.lbl.setText("Aguardando coleta")
        self.repintar()

    def repintar(self):
        self.lbl.setStyleSheet(
            f"color: {paleta.cor(self.acento)}; font-size: 13px;"
            " font-weight: 600; background: transparent;")
        self.update()

    def paintEvent(self, evento):
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.Antialiasing)
        area = QRectF(self.rect().adjusted(0, 0, -1, -1))
        pintor.setPen(QPen(QColor(paleta.tom_borda(self.acento)), 1))
        pintor.setBrush(QColor(paleta.tom_suave(self.acento)))
        pintor.drawRoundedRect(area, self.RAIO, self.RAIO)
        pintor.end()


class CartaoDestaque(_CartaoPintado):
    """
    O número-herói: h, sua incerteza e o veredicto, centralizados.

    Ocupa a largura toda de propósito. Depois de uma coleta de vários minutos,
    o resultado merece ser a primeira coisa que se enxerga da porta do
    laboratório — não uma linha de texto entre outras.
    """

    def __init__(self, parent=None):
        super().__init__("fotocorrente", parent)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

        coluna = QVBoxLayout(self)
        coluna.setContentsMargins(20, 22, 20, 20)
        coluna.setSpacing(4)

        self.lbl_titulo = _rotulo("CONSTANTE DE PLANCK", 11, 600, "#000000")
        self.lbl_valor = _rotulo("—", 42, 700, "#000000")
        self.lbl_incerteza = _rotulo("aguardando a coleta", 13, 400, "#000000")

        self.selo = SeloVeredicto()
        linha_selo = QHBoxLayout()
        linha_selo.addStretch()
        linha_selo.addWidget(self.selo)
        linha_selo.addStretch()

        coluna.addWidget(self.lbl_titulo)
        coluna.addWidget(self.lbl_valor)
        coluna.addWidget(self.lbl_incerteza)
        coluna.addSpacing(6)
        coluna.addLayout(linha_selo)
        self.repintar()

    def definir(self, resultado):
        """Recebe o `ResultadoAnalise` inteiro e se monta a partir dele."""
        from utils.error_models import decompor_com_incerteza

        partes = decompor_com_incerteza(resultado.h, resultado.incerteza_expandida)
        if partes is None:
            self.lbl_valor.setText(f"{resultado.h:.4e} J·s")
            self.lbl_incerteza.setText("incerteza indisponível para este ajuste")
        else:
            mantissa, mantissa_u, expoente, casas = partes
            potencia = f"× 10{sobrescrito(expoente)}"
            self.lbl_valor.setText(f"{mantissa:.{casas}f} {potencia} J·s")
            self.lbl_incerteza.setText(
                f"± {mantissa_u:.{casas}f} {potencia} J·s   ·   "
                f"incerteza expandida, k = {resultado.k:g}")

        self.selo.definir(
            resultado.compativel_com_codata,
            "Compatível com a CODATA" if resultado.compativel_com_codata
            else "CODATA fora da incerteza — há sistemático não contabilizado")
        self.acento = "bom" if resultado.compativel_com_codata else "atencao"
        self.repintar()

    def limpar(self):
        self.acento = "fotocorrente"
        self.lbl_valor.setText("—")
        self.lbl_incerteza.setText("aguardando a coleta")
        self.selo.limpar()
        self.repintar()

    def repintar(self):
        self.lbl_titulo.setStyleSheet(
            f"color: {paleta.cor('tinta_fraca')}; font-size: 11px;"
            " font-weight: 600; letter-spacing: 2px; background: transparent;")
        self.lbl_valor.setStyleSheet(
            f"color: {paleta.cor('tinta')}; font-size: 42px; font-weight: 700;"
            " background: transparent;")
        self.lbl_incerteza.setStyleSheet(
            f"color: {paleta.cor('tinta_fraca')}; font-size: 13px;"
            " background: transparent;")
        self.selo.repintar()
        self.update()


class BarraOrcamento(QWidget):
    """
    Proporção de cada fonte na incerteza, como faixa horizontal.

    Desenhada à mão porque é uma barra empilhada de uma linha só — não vale
    uma dependência de gráfico. Cada segmento tem 2 px de respiro, para que
    fronteiras entre faixas fiquem legíveis mesmo em cores próximas.
    """

    ALTURA = 14
    RESPIRO = 3

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(self.ALTURA)
        self._fatias = []

    def definir(self, fatias: list):
        """`fatias` é [(nome, percentual), ...] já ordenado."""
        self._fatias = list(fatias)
        self.update()

    def repintar(self):
        self.update()

    def paintEvent(self, evento):
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.Antialiasing)
        pintor.setPen(Qt.NoPen)

        if not self._fatias:
            pintor.setBrush(QColor(paleta.cor("borda")))
            pintor.drawRoundedRect(QRectF(0, 0, self.width(), self.ALTURA), 7, 7)
            pintor.end()
            return

        largura_util = self.width() - self.RESPIRO * (len(self._fatias) - 1)
        x = 0.0
        for indice, (_, percentual) in enumerate(self._fatias):
            largura = largura_util * percentual / 100.0
            pintor.setBrush(QColor(paleta.serie(indice)))
            pintor.drawRoundedRect(
                QRectF(x, 0, max(largura, 2.0), self.ALTURA), 7, 7)
            x += largura + self.RESPIRO
        pintor.end()


class LegendaOrcamento(QWidget):
    """Rótulos do orçamento: marcador colorido + nome + percentual, em texto."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.linha = QHBoxLayout(self)
        self.linha.setContentsMargins(0, 0, 0, 0)
        self.linha.setSpacing(16)
        self._fatias = []
        self.linha.addStretch()

    def definir(self, fatias: list):
        self._fatias = list(fatias)
        self.repintar()

    def repintar(self):
        while self.linha.count():
            item = self.linha.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.linha.addStretch()
        for indice, (nome, percentual) in enumerate(self._fatias):
            # O texto traz nome E percentual: a cor é reforço, não a informação.
            item = QLabel(f"■ {nome}  {percentual:.0f}%")
            item.setStyleSheet(f"color: {paleta.serie(indice)}; font-size: 12px;"
                               " font-weight: 500; background: transparent;")
            self.linha.addWidget(item)
        self.linha.addStretch()


# -- painel de registro ------------------------------------------------------

def estilo_terminal() -> str:
    """
    Folha de estilo do painel de registro.

    Fonte monoespaçada porque as colunas precisam alinhar, mas sem o verde
    sobre preto de terminal antigo: superfície discreta e tinta legível, do
    mesmo tom do resto da interface, em qualquer um dos dois temas.
    """
    return (f"QTextEdit {{ background-color: {paleta.cor('superficie_alt')};"
            f" color: {paleta.cor('tinta')};"
            f" border: 1px solid {paleta.cor('borda')}; border-radius: 8px;"
            f" padding: 10px;"
            f" selection-background-color: {paleta.cor('fotocorrente')};"
            f" font-family: 'Cascadia Mono', 'Consolas', monospace;"
            f" font-size: 12px; line-height: 150%; }}")


def linha_registro(tensao: float, corrente: float, temperatura: float,
                   fotocorrente: float, usado: bool) -> str:
    """
    Uma linha do registro, em HTML, com as colunas alinhadas.

    Pontos descartados saem esmaecidos e marcados com texto — de novo, a
    distinção não pode depender só da cor.
    """
    cor = paleta.cor("tinta") if usado else paleta.cor("descartado")
    marca = "" if usado else "  ·fora"
    return (f'<span style="color:{cor};">'
            f'{tensao:6.2f} V &nbsp;{corrente:6.3f} A &nbsp;'
            f'{temperatura:7.1f} K &nbsp;{fotocorrente:9.2e} A{marca}'
            f'</span>')


def cabecalho_registro() -> str:
    return (f'<span style="color:{paleta.cor("tinta_fraca")};">'
            f'{"tensão":>8} {"corrente":>9} {"temp.":>9} {"fotocorrente":>13}'
            f'</span>')
