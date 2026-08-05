# content/filamentos.py
"""
Presets de coeficientes de resistividade do filamento (A3).

Conteúdo é dado, não código: a UI só renderiza esta lista num ComboBox.

Cada preset traz a **fonte** dos números. Isso importa porque os coeficientes
entram diretamente no cálculo da temperatura e, por consequência, no valor de
h: adotar um par sem saber de onde veio é uma incerteza sistemática invisível.

R0 NÃO faz parte do preset. A resistência a frio é propriedade do filamento
específico que está na bancada, medida a cada montagem — não de um modelo
tabelado.

Na Fase 4 esta lista migra para `profiles/filamentos.json`, junto com os
perfis de LED, instrumentos e varredura.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class PresetFilamento:
    nome: str
    alpha: float   # coeficiente linear, K⁻¹
    beta: float    # coeficiente quadrático, K⁻²
    fonte: str
    observacao: str = ""

    @property
    def rotulo(self) -> str:
        return f"{self.nome}  (α={self.alpha:.3g}, β={self.beta:.3g})"


PRESETS_FILAMENTO = [
    PresetFilamento(
        nome="Padrão do software",
        alpha=5.23e-3,
        beta=7.0e-7,
        fonte="Origem não documentada",
        observacao=(
            "É o par que o software sempre usou e com o qual todas as coletas "
            "em data_backup/ foram processadas. Continua sendo o padrão para "
            "não invalidar o histórico — mas a procedência não está registrada, "
            "então prefira um preset com fonte citada em medidas novas."
        ),
    ),
    PresetFilamento(
        nome="Artigo RBEF / PHYWE",
        alpha=4.82e-3,
        beta=6.76e-7,
        fonte="Cavalcante & Haag (2005), Eq. 10 — dados PHYWE",
        observacao=(
            "Os valores usados no artigo de referência deste experimento. "
            "Diferem do padrão em cerca de 8% em α e 3% em β, o que desloca "
            "as temperaturas calculadas."
        ),
    ),
]

PRESET_PADRAO = PRESETS_FILAMENTO[0]
