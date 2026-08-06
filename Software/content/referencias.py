# content/referencias.py
"""
Referências bibliográficas e técnicas do projeto.

Conteúdo é dado, não código: a aba de Referências apenas renderiza esta lista.
Para acrescentar um documento, adicione uma Referencia aqui — a UI se adapta.

Os PDFs em `Docs/` foram conferidos contra a origem oficial em 05/08/2026:
os três documentos da Tektronix têm MD5 idêntico ao do arquivo servido por
download.tek.com, e o artigo do RBEF é de acesso aberto (SciELO/DOI).
"""
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Onde procurar a pasta Docs/ com as cópias locais:
# - rodando do repositório: na raiz dele (.../Software/content -> parents[2]);
# - no executável empacotado (PyInstaller), `__file__` aponta para dentro de
#   `_internal/` e subir três níveis cai fora da instalação — lá a referência
#   é a pasta do próprio executável, onde o instalador deposita Docs/.
if getattr(sys, "frozen", False):
    _RAIZ = Path(sys.executable).resolve().parent
else:
    _RAIZ = Path(__file__).resolve().parents[2]
PASTA_DOCS = _RAIZ / "Docs"


@dataclass(frozen=True)
class Referencia:
    """Um documento de referência do projeto."""

    titulo: str
    autoria: str            # autores ou instituição responsável
    publicacao: str         # onde/quando foi publicado
    identificador: str      # DOI, número de peça Tektronix, etc.
    arquivo_local: str      # nome do arquivo dentro de Docs/
    url_documento: str      # link direto para o documento oficial
    url_pagina: str         # página oficial que hospeda o documento
    acesso: str             # condição de acesso / direitos
    uso_no_software: str    # por que este documento importa aqui
    trechos_usados: list = field(default_factory=list)

    @property
    def caminho_local(self) -> Path:
        return PASTA_DOCS / self.arquivo_local

    @property
    def disponivel_localmente(self) -> bool:
        return self.caminho_local.is_file()


REFERENCIAS = [
    Referencia(
        titulo="Corpo negro e determinação experimental da constante de Planck",
        autoria="Marisa Almeida Cavalcante (PUC-SP) e Rafael Haag (UFRGS)",
        publicacao=(
            "Revista Brasileira de Ensino de Física, v. 27, n. 3, p. 343–348 (2005). "
            "Sociedade Brasileira de Física."
        ),
        identificador="DOI 10.1590/S1806-11172005000300007",
        arquivo_local="Corpo negro e determinação experimental da constante de Planck.pdf",
        url_documento="https://doi.org/10.1590/S1806-11172005000300007",
        url_pagina="https://www.scielo.br/j/rbef/a/P7GXWdsKZLsvgFJYKk6rMnH/?lang=pt",
        acesso="Acesso aberto (SciELO)",
        uso_no_software=(
            "É a base teórica de todo o experimento: o método de usar LEDs como "
            "sensores espectrais seletivos da radiação de um filamento de tungstênio, "
            "e a cadeia de contas que o software reproduz."
        ),
        trechos_usados=[
            "Eq. 1 — distribuição de Planck, e a aproximação de Wien que a lineariza",
            "Eq. 10–12 — R(T) do tungstênio e a solução por Bhaskara (calculate_temperature)",
            "Eq. 13 — h = −m·λ·k_B/c, a inclinação de ln(I) × 1/T (calculate_planck_constant)",
            "Seção 3.3 — largura espectral do LED, Δλ ≈ 25–35 nm (dominante na incerteza de h)",
            "Verificação da lei de Stefan-Boltzmann: log(V·i) × log(T), inclinação ≈ 4",
        ],
    ),
    Referencia(
        titulo="Digital Multimeters — Tektronix DMM4050 and DMM4040 Datasheet",
        autoria="Tektronix, Inc.",
        publicacao="Folha de dados do produto",
        identificador="Tektronix-DMM4050-and-DMM4040-Digital-Multimeter-Datasheet-8",
        arquivo_local="Tektronix-DMM4050-and-DMM4040-Digital-Multimeter-Datasheet-8.pdf",
        url_documento=(
            "https://download.tek.com/datasheet/"
            "Tektronix-DMM4050-and-DMM4040-Digital-Multimeter-Datasheet-8.pdf"
        ),
        url_pagina="https://www.tek.com/en/datasheet/dmm4050-4040-digital-multimeter",
        acesso="Distribuição livre pelo fabricante",
        uso_no_software=(
            "Define o erro instrumental da fotocorrente do LED — o multímetro que "
            "lê a corrente na faixa fixa de 100 µA."
        ),
        trechos_usados=[
            "Tabela de exatidão de corrente DC: faixa de 100 µA, ±(0,05% da leitura "
            "+ 0,025% da faixa) — o termo de faixa vale 25 nA",
            "Resolução de 6½ dígitos: 100 pA",
            "É este piso de 25 nA que torna os pontos de baixa temperatura pouco "
            "informativos e justifica a regressão ponderada",
        ],
    ),
    Referencia(
        titulo=(
            "PWS4205, PWS4305, PWS4323, PWS4602 e PWS4721 Linear DC Power Supplies — "
            "Specifications and Performance Verification (Technical Reference)"
        ),
        autoria="Tektronix, Inc.",
        publicacao="Manual técnico do produto",
        identificador="Peça Tektronix 077-0480-00",
        arquivo_local="PWS4205, PWS4305, PWS4323, PWS4602, and PWS4721.pdf",
        url_documento="https://download.tek.com/manual/077048000_web.pdf",
        url_pagina=(
            "https://www.tek.com/en/manual/dc-power-supply/"
            "pws4205-pws4305-pws4323-pws4602-and-pws4721-pws4000-dc-power-supply"
        ),
        acesso="Distribuição livre pelo fabricante",
        uso_no_software=(
            "Define o erro da tensão e da corrente do filamento — e portanto o erro "
            "de R, que se propaga para a temperatura e para h."
        ),
        trechos_usados=[
            "Faixa do PWS4323: 0–32 V, 0–3 A",
            "Exatidão de leitura (readback) de tensão e de corrente",
            "Exatidão de programação (setting) de tensão — pior que a de readback, "
            "razão pela qual a fonte deve ser lida com MEAS:VOLT? em vez de se "
            "confiar no valor programado",
        ],
    ),
    Referencia(
        titulo="TekVISA Programmer Manual",
        autoria="Tektronix, Inc.",
        publicacao="Manual do programador",
        identificador="Peça Tektronix 077-0140-00",
        arquivo_local="Tektronix Visa Documentation.pdf",
        url_documento="https://download.tek.com/manual/077014000web.pdf",
        url_pagina=(
            "https://www.tek.com/en/support/software/driver/"
            "tekvisa-connectivity-software-v5111"
        ),
        acesso="Distribuição livre pelo fabricante",
        uso_no_software=(
            "Documenta a camada VISA sobre a qual o PyVISA conversa com os dois "
            "instrumentos, e o formato das strings de recurso usadas no software."
        ),
        trechos_usados=[
            "Sintaxe dos endereços de recurso: USB::… para a fonte e "
            "TCPIP::<ip>::3490::SOCKET para o multímetro",
            "Comportamento de terminação de linha em conexões SOCKET "
            "(o '\\n' que os drivers configuram)",
            "Comandos SCPI comuns: *IDN?, *CLS, SYST:REM, SYST:LOC",
        ],
    ),
]
