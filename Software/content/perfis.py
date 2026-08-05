# content/perfis.py
"""
Sistema modular de perfis (Fase 4).

Quatro famílias de parâmetros plugáveis, cada uma em um JSON versionável
dentro de `Software/profiles/`:

    leds.json          λ ± Δλ do sensor
    filamentos.json    coeficientes α e β do tungstênio
    instrumentos.json  especificações de exatidão (alimentam error_models)
    varreduras.json    presets de faixa, passo, espera e leituras por ponto

Três decisões de projeto:

1. **Todo perfil carrega a sua FONTE.** Um número sem procedência é uma
   incerteza sistemática invisível. O campo é obrigatório; quando a origem é
   desconhecida, isso fica escrito.

2. **O JSON manda, mas nunca quebra o software.** Se o arquivo não existir,
   estiver corrompido ou vier com campos faltando, o carregador cai para os
   padrões embutidos e segue. Um laboratório não pode ficar sem coletar porque
   alguém errou uma vírgula num JSON.

3. **R0 NÃO é perfil.** A resistência a frio é propriedade do filamento
   específico que está na bancada, medida a cada montagem — não de um modelo
   tabelado. Continua sendo campo de experimento.
"""
import json
from dataclasses import dataclass, asdict, field
from pathlib import Path

# .../Software/content/perfis.py -> parents[1] = Software/
PASTA_PERFIS = Path(__file__).resolve().parents[1] / "profiles"


# =============================================================================
# Os quatro tipos de perfil
# =============================================================================

@dataclass(frozen=True)
class PerfilLed:
    nome: str
    lambda_nm: float
    delta_lambda_nm: float
    fonte: str
    observacao: str = ""

    @property
    def rotulo(self) -> str:
        return f"{self.nome}  ({self.lambda_nm:g} ± {self.delta_lambda_nm:g} nm)"


@dataclass(frozen=True)
class PerfilFilamento:
    nome: str
    alpha: float          # K⁻¹
    beta: float           # K⁻²
    fonte: str
    observacao: str = ""

    @property
    def rotulo(self) -> str:
        return f"{self.nome}  (α={self.alpha:.3g}, β={self.beta:.3g})"


@dataclass(frozen=True)
class PerfilInstrumento:
    nome: str
    grandeza: str         # "fotocorrente", "tensao_fonte", "corrente_fonte"
    pct_leitura: float
    termo_fixo: float
    unidade: str
    fonte: str
    distribuicao: str = "retangular"
    observacao: str = ""

    @property
    def rotulo(self) -> str:
        return f"{self.nome}  (±{self.pct_leitura*100:g}% + {self.termo_fixo:g} {self.unidade})"

    def como_especificacao(self):
        """Converte para a EspecificacaoInstrumento usada em error_models."""
        from utils.error_models import (EspecificacaoInstrumento,
                                        DIVISOR_RETANGULAR, DIVISOR_TRIANGULAR)
        divisor = (DIVISOR_TRIANGULAR if self.distribuicao == "triangular"
                   else DIVISOR_RETANGULAR)
        return EspecificacaoInstrumento(
            nome=self.nome, pct_leitura=self.pct_leitura,
            termo_fixo=self.termo_fixo, unidade=self.unidade,
            fonte=self.fonte, divisor=divisor)


@dataclass(frozen=True)
class PerfilVarredura:
    nome: str
    v_start: float
    v_end: float
    v_step: float
    delay_ms: float
    n_leituras: int = 1
    t_minima: float = 1800.0
    observacao: str = ""

    @property
    def rotulo(self) -> str:
        return (f"{self.nome}  ({self.v_start:g}–{self.v_end:g} V, "
                f"passo {self.v_step:g})")


# =============================================================================
# Padrões embutidos — a rede de segurança
# =============================================================================

PADROES = {
    "leds": [
        PerfilLed("Amarelo 590 nm", 590.0, 30.0,
                  "Cavalcante & Haag (2005), seção 3.3 — Δλ de 25 a 35 nm",
                  "O LED usado na montagem de referência do artigo."),
        PerfilLed("Vermelho 660 nm", 660.0, 30.0,
                  "Faixa típica de LED vermelho; Δλ do artigo",
                  "Confirme λ com o datasheet do componente específico."),
        PerfilLed("Verde 525 nm", 525.0, 35.0,
                  "Faixa típica de LED verde; Δλ do artigo",
                  "λ mais curto favorece a aproximação de Wien."),
    ],
    "filamentos": [
        PerfilFilamento("Padrão do software", 5.23e-3, 7.0e-7,
                        "Origem não documentada — ver PENDENCIAS.txt, P1",
                        "É o par com que TODAS as coletas em data_backup/ foram "
                        "processadas. Continua padrão para não invalidar o "
                        "histórico, mas prefira um preset com fonte citada."),
        PerfilFilamento("Artigo RBEF / PHYWE", 4.82e-3, 6.76e-7,
                        "Cavalcante & Haag (2005), Eq. 10 — dados PHYWE",
                        "Valores do artigo de referência. Diferem do padrão em "
                        "~8% em α e ~3% em β."),
    ],
    "instrumentos": [
        PerfilInstrumento("DMM4050 — 100 µA, 1 ano", "fotocorrente",
                          0.0005, 25e-9, "A",
                          "Tektronix DMM4050/DMM4040 Datasheet, DC Current",
                          observacao="0,05% da leitura + 0,025% da faixa de 100 µA."),
        PerfilInstrumento("PWS4323 — readback de tensão", "tensao_fonte",
                          0.0002, 3e-3, "V",
                          "Tektronix 077-0480-00, Tabela 1"),
        PerfilInstrumento("PWS4323 — readback de corrente", "corrente_fonte",
                          0.0005, 2e-3, "A",
                          "Tektronix 077-0480-00, Tabela 1"),
    ],
    "varreduras": [
        PerfilVarredura("Bancada — padrão", 1.0, 10.0, 0.5, 3000.0, 1, 1800.0,
                        "Faixa conservadora, uma leitura por ponto."),
        PerfilVarredura("Bancada — completa 0–12 V", 0.0, 12.0, 0.25, 3000.0, 1, 1800.0,
                        "Registra o filamento inteiro; o corte de 1800 K "
                        "protege a regressão dos pontos frios."),
        PerfilVarredura("Bancada — alta precisão", 6.0, 12.0, 0.2, 4000.0, 5, 1800.0,
                        "Só a região de Wien, com 5 leituras por ponto para "
                        "obter incerteza Tipo A. Demora bem mais."),
        PerfilVarredura("Simulação — rápida", 0.5, 12.0, 0.1, 50.0, 1, 1800.0,
                        "Para a aba de simulação, sem espera térmica real."),
    ],
}

_CLASSES = {
    "leds": PerfilLed,
    "filamentos": PerfilFilamento,
    "instrumentos": PerfilInstrumento,
    "varreduras": PerfilVarredura,
}


# =============================================================================
# Carga e gravação
# =============================================================================

class AvisoPerfil(Exception):
    """Problema ao ler um arquivo de perfis (não interrompe o software)."""


_avisos: list = []


def avisos() -> list:
    """Problemas encontrados na última carga — a UI mostra ao operador."""
    return list(_avisos)


def _caminho(tipo: str) -> Path:
    return PASTA_PERFIS / f"{tipo}.json"


def carregar_perfis(tipo: str) -> list:
    """
    Lê os perfis de um tipo do JSON, caindo para os padrões em caso de problema.

    Nunca levanta exceção: os avisos ficam registrados em `avisos()` e a
    coleta pode seguir com os valores embutidos.
    """
    if tipo not in _CLASSES:
        raise KeyError(f"Tipo de perfil desconhecido: {tipo}")

    classe = _CLASSES[tipo]
    caminho = _caminho(tipo)

    if not caminho.is_file():
        return list(PADROES[tipo])

    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        if not isinstance(dados, list):
            raise AvisoPerfil("o arquivo não contém uma lista de perfis")

        perfis, ignorados = [], 0
        for item in dados:
            try:
                perfis.append(classe(**item))
            except TypeError:
                ignorados += 1

        if ignorados:
            _avisos.append(
                f"{caminho.name}: {ignorados} perfil(is) com campos inválidos "
                "foram ignorados.")
        if not perfis:
            _avisos.append(f"{caminho.name}: nenhum perfil válido; usando os padrões.")
            return list(PADROES[tipo])
        return perfis

    except (json.JSONDecodeError, AvisoPerfil, OSError) as erro:
        _avisos.append(f"{caminho.name}: {erro}. Usando os perfis padrão.")
        return list(PADROES[tipo])


def salvar_perfis(tipo: str, perfis: list) -> Path:
    """Grava a lista inteira de um tipo, criando a pasta se preciso."""
    if tipo not in _CLASSES:
        raise KeyError(f"Tipo de perfil desconhecido: {tipo}")
    PASTA_PERFIS.mkdir(parents=True, exist_ok=True)
    caminho = _caminho(tipo)
    caminho.write_text(
        json.dumps([asdict(p) for p in perfis], indent=2, ensure_ascii=False),
        encoding="utf-8")
    return caminho


def acrescentar_perfil(tipo: str, perfil) -> Path:
    """Acrescenta um perfil personalizado, substituindo outro de mesmo nome."""
    atuais = [p for p in carregar_perfis(tipo) if p.nome != perfil.nome]
    atuais.append(perfil)
    return salvar_perfis(tipo, atuais)


def escrever_padroes_se_ausente() -> list:
    """
    Materializa os JSONs a partir dos padrões, para o usuário poder editá-los.

    Só cria o que não existe — nunca sobrescreve edição do operador.
    """
    criados = []
    for tipo, perfis in PADROES.items():
        if not _caminho(tipo).is_file():
            criados.append(salvar_perfis(tipo, perfis))
    return criados


def perfil_por_nome(tipo: str, nome: str):
    """Busca um perfil pelo nome; devolve None se não houver."""
    for perfil in carregar_perfis(tipo):
        if perfil.nome == nome:
            return perfil
    return None


def especificacoes_de_instrumentos() -> dict:
    """
    Mapa grandeza → EspecificacaoInstrumento, para alimentar error_models.

    Se houver mais de um perfil para a mesma grandeza, o primeiro vence.
    """
    especificacoes = {}
    for perfil in carregar_perfis("instrumentos"):
        especificacoes.setdefault(perfil.grandeza, perfil.como_especificacao())
    return especificacoes
