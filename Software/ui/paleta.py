# ui/paleta.py
"""
Tema e paleta de cores da interface.

Três razões para isto existir como módulo, em vez de cores soltas nos widgets:

**Tema claro e escuro, escolhidos pelo operador.** O software é usado em aula
(projetor, sala acesa) e na bancada (laboratório). Cada situação pede uma
luminosidade diferente, então o tema é preferência do usuário, guardada entre
sessões. O padrão é o CLARO: é o que sobrevive a um projetor, e era o pedido —
a interface anterior era "preta e cinza demais".

**Cor com significado fixo.** Cada grandeza do experimento tem SEMPRE a mesma
cor: temperatura em laranja, fotocorrente em azul, regressão em roxo, pontos
descartados em cinza. Quem olhou um gráfico reconhece a série no gráfico
seguinte, e no cartão de resultado, sem reler a legenda. As cores de estado
(verde / âmbar / vermelho) são RESERVADAS — nunca viram "série 4".

**Um só lugar para trocar.** Ao alternar o tema, tudo que foi pintado à mão
precisa ser repintado: gráficos do pyqtgraph, painéis de registro, cartões.
Centralizar as cores aqui é o que torna esse repinte possível.

Nenhuma cor carrega informação sozinha: todo ponto que usa cor de estado traz
também ícone e texto, para quem não distingue vermelho de verde.
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

import pyqtgraph as pg
from qfluentwidgets import setTheme, setThemeColor, Theme, isDarkTheme

from core.hardware_manager import preferencias

CHAVE_TEMA = "Appearance/Tema"
TEMA_PADRAO = "claro"

# Acento da própria biblioteca Fluent (botões primários, seleção, foco).
ACENTO = {"claro": "#0F6CBD", "escuro": "#4CA3E8"}

_PALETAS = {
    # Claro: superfícies brancas sobre um cinza levemente azulado, tinta quase
    # preta. Os acentos são versões mais escuras/saturadas, porque cor clara
    # sobre fundo claro perde contraste.
    "claro": {
        "superficie":      "#FFFFFF",
        "superficie_alt":  "#F3F6FA",
        "tinta":           "#14171C",
        "tinta_fraca":     "#5B6470",
        "borda":           "#DDE3EB",
        "grafico_fundo":   "#FFFFFF",
        "grafico_tinta":   "#48515E",
        "grafico_grade":   "#C9D2DD",

        "temperatura":     "#E8710A",
        "fotocorrente":    "#0F6CBD",
        "regressao":       "#7B1FA2",
        "descartado":      "#98A2B3",

        "bom":             "#137333",
        "atencao":         "#B06000",
        "ruim":            "#C5221F",
        "info":            "#00796B",
    },
    # Escuro: sai do preto puro (#121212) para um grafite azulado. O preto puro
    # era o que dava a impressão de "software apagado"; um cinza com temperatura
    # mantém o modo escuro sem o efeito de buraco.
    "escuro": {
        "superficie":      "#242A33",
        "superficie_alt":  "#1B2027",
        "tinta":           "#E7EAF0",
        "tinta_fraca":     "#9BA5B4",
        "borda":           "#37404C",
        "grafico_fundo":   "#1B2027",
        "grafico_tinta":   "#B7C0CD",
        "grafico_grade":   "#3A434F",

        "temperatura":     "#FFA726",
        "fotocorrente":    "#4CA3E8",
        "regressao":       "#C77DDB",
        "descartado":      "#6E7885",

        "bom":             "#5CC46A",
        "atencao":         "#FFB74D",
        "ruim":            "#F0716B",
        "info":            "#4DB6AC",
    },
}

# Faixas do orçamento de incertezas. Ordem fixa, atribuída por POSIÇÃO e não por
# rodízio, para que a mesma fonte tenha sempre a mesma cor entre coletas.
_SERIES = {
    "claro":  ["#0F6CBD", "#7B1FA2", "#00796B", "#C5221F", "#6D4C41", "#B06000"],
    "escuro": ["#4CA3E8", "#C77DDB", "#4DB6AC", "#F0716B", "#BCAAA4", "#FFB74D"],
}


# -- estado ------------------------------------------------------------------

def nome_tema() -> str:
    """Tema guardado nas preferências ('claro' ou 'escuro')."""
    valor = preferencias().value(CHAVE_TEMA, TEMA_PADRAO, type=str)
    return valor if valor in _PALETAS else TEMA_PADRAO


def escuro() -> bool:
    return nome_tema() == "escuro"


def aplicar_tema(nome: str = None, guardar: bool = True) -> str:
    """
    Aplica o tema à biblioteca Fluent e ao pyqtgraph, e o guarda.

    Chamada uma vez na abertura da janela e a cada alternância. O pyqtgraph
    precisa entrar aqui porque suas opções globais só valem para gráficos
    criados DEPOIS — os já existentes são repintados por `pintar_grafico`.

    `guardar=False` aplica sem mexer na preferência: é o caso da janela
    clássica, que é escura por construção e não deve arrastar a escolha do
    operador na janela nova junto com ela.
    """
    nome = nome if nome in _PALETAS else nome_tema()
    if guardar:
        preferencias().setValue(CHAVE_TEMA, nome)

    # ORDEM IMPORTA, e custou uma sessão descobrir: o esquema de cor vem
    # PRIMEIRO. `setTheme` repolimenta todos os widgets da biblioteca, e cada
    # repolimento congela a paleta da aplicação vigente naquele instante. Com o
    # esquema aplicado depois, os widgets nativos ficavam uma troca ATRASADOS —
    # a lista de coletas aparecia preta no tema claro e o painel de referências
    # branco no escuro. Aplicar o esquema antes faz o repolimento já pegar a
    # paleta certa.
    _alinhar_widgets_nativos(nome)
    setTheme(Theme.DARK if nome == "escuro" else Theme.LIGHT)
    setThemeColor(ACENTO[nome])

    pg.setConfigOption('background', _PALETAS[nome]["grafico_fundo"])
    pg.setConfigOption('foreground', _PALETAS[nome]["grafico_tinta"])
    return nome


def _alinhar_widgets_nativos(nome: str):
    """
    Faz os widgets Qt comuns obedecerem ao tema do software.

    Nem tudo na interface é widget da biblioteca Fluent: a página de Parâmetros
    é feita de `QLineEdit`, `QComboBox` e `QGroupBox` comuns, e há `QListWidget`
    e `QTextEdit` na Análise. Desde o Qt 6.5 esses widgets seguem o modo de cor
    do SISTEMA, não o nosso — numa máquina com o Windows em modo escuro, a
    página de Parâmetros continuava preta mesmo com o tema claro escolhido, o
    que dava uma interface metade clara e metade escura.

    Fixar o esquema de cor da aplicação resolve para todos de uma vez. É
    condicional porque `setColorScheme` só existe do Qt 6.8 em diante; onde não
    houver, a interface continua funcionando, apenas com essa mistura.
    """
    app = QApplication.instance()
    if app is None:
        return
    dicas = app.styleHints()
    if not hasattr(dicas, "setColorScheme"):
        return
    dicas.setColorScheme(Qt.ColorScheme.Dark if nome == "escuro"
                         else Qt.ColorScheme.Light)


def alternar_tema() -> str:
    """Troca claro ↔ escuro e devolve o nome do tema que passou a valer."""
    return aplicar_tema("claro" if escuro() else "escuro")


# -- consulta ----------------------------------------------------------------

def cor(chave: str) -> str:
    """
    Cor da paleta em vigor, em hexadecimal.

    Lê o tema pela biblioteca (`isDarkTheme`) e não pelas preferências: assim a
    resposta acompanha o que está desenhado na tela mesmo que algo tenha
    chamado `setTheme` diretamente.
    """
    tema = "escuro" if isDarkTheme() else "claro"
    return _PALETAS[tema].get(chave, _PALETAS[tema]["tinta"])


def serie(indice: int) -> str:
    """Cor da n-ésima série de um gráfico ou faixa do orçamento."""
    tema = "escuro" if isDarkTheme() else "claro"
    cores = _SERIES[tema]
    return cores[indice % len(cores)]


def mesclar(frente: str, fundo: str, fracao: float) -> str:
    """Mistura duas cores; `fracao` é o quanto da frente aparece."""
    a, b = QColor(frente), QColor(fundo)
    ponto = lambda x, y: max(0, min(255, round(y + (x - y) * fracao)))
    return QColor(ponto(a.red(), b.red()),
                  ponto(a.green(), b.green()),
                  ponto(a.blue(), b.blue())).name()


def tom_suave(chave: str) -> str:
    """
    Fundo tingido pela cor de uma grandeza — a superfície dos cartões.

    Mistura opaca em vez de transparência: o valor final é calculado aqui e sai
    como cor sólida, então não depende de o widget-pai pintar nada atrás.
    """
    fracao = 0.12 if isDarkTheme() else 0.09
    return mesclar(cor(chave), cor("superficie"), fracao)


def tom_borda(chave: str) -> str:
    """Borda do cartão: a mesma cor, um pouco mais presente que o fundo."""
    fracao = 0.34 if isDarkTheme() else 0.26
    return mesclar(cor(chave), cor("borda"), fracao)


# -- gráficos ----------------------------------------------------------------

def pincel(chave: str, alfa: int = 215):
    """Pincel do pyqtgraph com a cor de uma grandeza."""
    tinta = QColor(cor(chave))
    tinta.setAlpha(alfa)
    return pg.mkBrush(tinta)


def caneta_reta():
    """Caneta da reta de regressão — tracejada, na cor da regressão."""
    from PySide6.QtCore import Qt
    return pg.mkPen(QColor(cor("regressao")), width=2, style=Qt.DashLine)


def pintar_grafico(grafico, titulo: str = None, item=None):
    """
    Repinta um gráfico JÁ EXISTENTE com as cores do tema em vigor.

    `pg.setConfigOption` só afeta gráficos criados depois dela; ao alternar o
    tema com a janela aberta, os gráficos na tela continuariam escuros sobre
    uma interface clara. Esta função percorre fundo, eixos, grade, título e
    legenda e acerta todos.

    `item` só é necessário para o `GraphicsLayoutWidget`, que é um contêiner e
    pode ter vários gráficos dentro — nele não há um "o" gráfico a descobrir.
    """
    grafico.setBackground(cor("grafico_fundo"))
    if item is None:
        item = grafico.getPlotItem() if hasattr(grafico, "getPlotItem") else grafico

    caneta = pg.mkPen(QColor(cor("grafico_tinta")))
    for lado in ("left", "bottom", "right", "top"):
        eixo = item.getAxis(lado)
        if eixo is None:
            continue
        eixo.setPen(caneta)
        eixo.setTextPen(caneta)

    item.showGrid(x=True, y=True, alpha=0.22 if isDarkTheme() else 0.30)

    if titulo is None:
        rotulo = getattr(item, "titleLabel", None)
        titulo = getattr(rotulo, "text", None) if rotulo is not None else None
    if titulo:
        item.setTitle(titulo, color=cor("tinta"), size="10pt")

    legenda = getattr(item, "legend", None)
    if legenda is not None:
        legenda.setLabelTextColor(cor("tinta"))
