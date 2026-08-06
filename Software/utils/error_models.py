# utils/error_models.py
"""
Teoria de erros: incertezas, propagação e ajuste ponderado (Fase 3).

Este módulo é escrito para ser AUDITADO, não só executado. Cada função traz a
equação que implementa e a hipótese que assume. A nomenclatura segue o GUM
(Guide to the Expression of Uncertainty in Measurement).

================================================================================
1. VOCABULÁRIO
================================================================================

Incerteza Tipo A — estimada por meios estatísticos, a partir da repetição da
    medida. Para N leituras de média x̄ e desvio padrão amostral s:

        u_A = s / √N                                                    (E1)

Incerteza Tipo B — estimada por qualquer outro meio; aqui, pela especificação
    do fabricante. Um datasheet que promete ±(a% da leitura + b da faixa) está
    declarando um LIMITE, não um desvio padrão. Sem informação adicional sobre
    a forma da distribuição dentro desse limite, o GUM manda assumir
    distribuição retangular, cuja incerteza padrão é:

        u_B = a / √3                                                    (E2)

Incerteza combinada — as duas são independentes, então somam em quadratura:

        u = √(u_A² + u_B²)                                              (E3)

Propagação — para f(x, y, ...) com variáveis INDEPENDENTES:

        u_f² = (∂f/∂x)² u_x² + (∂f/∂y)² u_y² + ...                      (E4)

Incerteza expandida — para declarar um intervalo de confiança:

        U = k · u_c        (k = 2 → aproximadamente 95%)                (E5)

================================================================================
2. A CADEIA DESTE EXPERIMENTO
================================================================================

    u(V), u(i)  ← especificação de readback da fonte              [E2]
        └── R = V/i − R_cabos                                     [E4 → E8]
              └── T = Bhaskara(R, R0, α, β)                       [E4 → E9..E12]
                    └── x = 1/T,  u_x = u_T/T²                    [E13]
    u(I_led)    ← especificação do multímetro ⊕ repetições        [E2, E3]
        └── y = ln(I_led),  u_y = u_I/I                           [E14]
              └── ajuste ponderado  →  m ± u_m                    [E15..E20]
                    └── h = −m λ k_B/c                            [E21]
                          (u_h/h)² = (u_m/m)² + (u_λ/λ)²          [E22]

A incerteza de λ costuma DOMINAR: a largura espectral do LED é de dezenas de
nanômetros sobre um λ de ~590 nm, ou seja, alguns por cento — bem acima do que
a regressão contribui num ajuste bom.

================================================================================
3. HIPÓTESES ASSUMIDAS (o que levar ao orientador — ver PENDENCIAS.txt, P2)
================================================================================

H1. Especificações de datasheet tratadas como limite de distribuição
    retangular (divisor √3). Convenção do GUM na ausência de outra informação.
H2. Largura espectral do LED tratada também como retangular.
H3. Variáveis consideradas independentes: nenhuma correlação entre V e i,
    embora venham do mesmo instrumento. Ignorar correlação é a hipótese mais
    frágil desta implementação.
H3b. ALEATÓRIO vs SISTEMÁTICO — a distinção mais importante daqui.
    Nem toda incerteza pode entrar no peso de um ponto. R0, α e β são os
    MESMOS para toda a varredura: errar R0 desloca todas as temperaturas na
    mesma direção, não espalha os pontos. Colocá-los no peso individual seria
    dizer ao ajuste que cada ponto flutua sozinho quanto o conjunto se desloca
    junto — o que infla os pesos e derruba o χ² reduzido artificialmente.

    Por isso a implementação separa:
      · ALEATÓRIAS (entram no peso de cada ponto): leitura de V e i, que
        variam ponto a ponto, e a fotocorrente com seu Tipo A;
      · SISTEMÁTICAS (propagadas por sensibilidade, ao final): R0, α, β e λ.

    Para cada sistemática, o software refaz o ajuste com o parâmetro deslocado
    de +u e mede o quanto h se move. Essa é a contribuição dela. É o mesmo
    espírito do GUM (∂f/∂x·u_x), obtido numericamente porque a dependência de
    h em R0 passa por dentro do ajuste e não tem forma fechada simples.
H3c. As especificações de datasheet são tratadas como aleatórias por ponto.
    Rigorosamente elas misturam uma parte sistemática (offset de calibração,
    igual para toda a varredura) com uma aleatória (ruído de leitura). Separá-
    las exigiria informação que o datasheet não fornece.
H4. Fator de abrangência k = 2 fixo, e não t de Student com graus de liberdade
    efetivos (Welch-Satterthwaite).
H5. Coeficientes α e β tratados como exatos por padrão (o software aceita
    incerteza para eles, mas não há valor tabelado de origem conhecida).
H6. Erros sistemáticos NÃO entram no orçamento: emissividade do tungstênio
    (corpo cinza, não negro), reflexões na montagem, alinhamento LED-filamento
    e gradiente de temperatura ao longo do filamento.
"""
import math
from dataclasses import dataclass, field

import numpy as np

from utils.math_models import (C, K_B, H_REF, calculate_temperature,
                               selecionar_pontos_validos,
                               TEMPERATURA_MINIMA_PADRAO)

# Divisor da distribuição retangular (E2). Um limite `a` uniformemente
# provável dentro de [−a, +a] tem variância a²/3.
DIVISOR_RETANGULAR = math.sqrt(3.0)

# Divisor da distribuição triangular, oferecido como alternativa: usado quando
# se tem razão para crer que valores centrais são mais prováveis.
DIVISOR_TRIANGULAR = math.sqrt(6.0)

FATOR_ABRANGENCIA_PADRAO = 2.0     # k = 2, ~95% (E5)

# Largura espectral típica de LED, do artigo (seção 3.3): 25 a 35 nm.
DELTA_LAMBDA_PADRAO_NM = 30.0

# Incerteza assumida para a leitura da temperatura ambiente, quando o operador
# não informa outra. Um termômetro de laboratório comum erra alguns graus.
INCERTEZA_TEMPERATURA_AMBIENTE = 2.0   # °C


# =============================================================================
# Especificações de instrumento
# =============================================================================

@dataclass(frozen=True)
class EspecificacaoInstrumento:
    """
    Uma linha de tabela de exatidão de datasheet.

    A forma universal é ±(percentual da leitura + termo fixo), onde o termo
    fixo costuma ser expresso como percentual do fundo de escala e aqui já
    entra convertido para a unidade da grandeza.

        limite(x) = pct_leitura · |x| + termo_fixo                      (E6)
        u(x)      = limite(x) / divisor                                 (E2)
    """

    nome: str
    pct_leitura: float      # fração (0.0005 = 0,05% da leitura)
    termo_fixo: float       # na unidade da grandeza
    unidade: str
    fonte: str
    divisor: float = DIVISOR_RETANGULAR

    def limite(self, leitura: float) -> float:
        """O ±(...) do datasheet, equação (E6)."""
        return self.pct_leitura * abs(leitura) + self.termo_fixo

    def incerteza_padrao(self, leitura) -> float:
        """Incerteza padrão Tipo B, equação (E2). Aceita escalar ou vetor."""
        return self.limite(np.asarray(leitura, dtype=float)) / self.divisor


# Valores extraídos dos datasheets — ver a aba Referências do software.
DMM4050_CORRENTE_100UA = EspecificacaoInstrumento(
    nome="DMM4050 — corrente DC, faixa 100 µA (1 ano, 23±5 °C)",
    pct_leitura=0.0005,      # 0,05% da leitura
    termo_fixo=25e-9,        # 0,025% da faixa de 100 µA = 25 nA
    unidade="A",
    fonte="Tektronix DMM4050/DMM4040 Datasheet, tabela de exatidão DC Current",
)

PWS4323_TENSAO_READBACK = EspecificacaoInstrumento(
    nome="PWS4323 — readback de tensão (25±5 °C)",
    pct_leitura=0.0002,      # 0,02% da leitura
    termo_fixo=3e-3,         # 3 mV
    unidade="V",
    fonte="Tektronix 077-0480-00, Tabela 1",
)

PWS4323_CORRENTE_READBACK = EspecificacaoInstrumento(
    nome="PWS4323 — readback de corrente (25±5 °C)",
    pct_leitura=0.0005,      # 0,05% da leitura
    termo_fixo=2e-3,         # 2 mA
    unidade="A",
    fonte="Tektronix 077-0480-00, Tabela 1",
)


# =============================================================================
# Tipo A — repetição
# =============================================================================

def incerteza_tipo_a(leituras) -> tuple:
    """
    Média e incerteza Tipo A de um conjunto de leituras repetidas, eq. (E1).

    Devolve (média, u_A). Com uma única leitura não há informação estatística:
    u_A = 0, e toda a incerteza fica por conta do Tipo B.

    Usa desvio padrão AMOSTRAL (ddof=1), porque estimamos a média a partir da
    própria amostra — usar ddof=0 subestimaria a dispersão.
    """
    leituras = np.asarray(leituras, dtype=float)
    n = leituras.size
    if n == 0:
        return float("nan"), float("nan")
    if n == 1:
        return float(leituras[0]), 0.0
    return float(np.mean(leituras)), float(np.std(leituras, ddof=1) / math.sqrt(n))


def combinar(u_a: float, u_b: float) -> float:
    """Combinação em quadratura de contribuições independentes, eq. (E3)."""
    return math.hypot(u_a, u_b)


# =============================================================================
# B6 — o limiar de corrente sai do instrumento, não de um palpite
# =============================================================================

def limiar_corrente_confiavel(spec: EspecificacaoInstrumento = DMM4050_CORRENTE_100UA,
                              razao_sinal_ruido: float = 1.0) -> float:
    """
    Menor corrente que ainda carrega informação, derivada da especificação.

    Uma leitura só significa alguma coisa quando o valor medido supera a
    própria margem de erro do instrumento. Exigindo que o sinal seja pelo menos
    `razao_sinal_ruido` vezes o limite de exatidão:

        I ≥ s · (pct·I + fixo)
        I · (1 − s·pct) ≥ s · fixo
        I ≥ s · fixo / (1 − s·pct)                                      (E7)

    Com o DMM4050 na faixa de 100 µA e s = 1, dá ≈ 25 nA — exatamente o termo
    de fundo do datasheet, como esperado.

    Este número substitui o antigo limiar de 1 nA, que era arbitrário e, pior,
    MENOR que o próprio ruído de fundo do instrumento: ele não descartava nada.

    O limiar é deliberadamente pouco agressivo (s = 1). Não precisa ser
    agressivo porque a regressão é PONDERADA: pontos de sinal fraco entram com
    peso pequeno em vez de serem descartados. O corte serve só para eliminar o
    que é indistinguível de zero — e o que quebraria o logaritmo.
    """
    denominador = 1.0 - razao_sinal_ruido * spec.pct_leitura
    if denominador <= 0:
        raise ValueError("Razão sinal/ruído incompatível com a especificação.")
    return razao_sinal_ruido * spec.termo_fixo / denominador


# =============================================================================
# Propagação: resistência e temperatura
# =============================================================================

def incerteza_resistencia(tensao, corrente, u_tensao, u_corrente,
                          u_r_cabos: float = 0.0):
    """
    Incerteza de R = V/i − R_cabos.

    Para um quociente, as incertezas RELATIVAS é que somam em quadrature (E4):

        (u_{V/i} / (V/i))² = (u_V/V)² + (u_i/i)²                        (E8)

    A resistência dos cabos é subtraída, então sua incerteza entra direto:

        u_R² = u_{V/i}² + u_{R_cabos}²
    """
    tensao = np.asarray(tensao, dtype=float)
    corrente = np.asarray(corrente, dtype=float)

    with np.errstate(divide="ignore", invalid="ignore"):
        quociente = tensao / corrente
        relativa = np.sqrt((u_tensao / tensao) ** 2 + (u_corrente / corrente) ** 2)
        u_quociente = np.abs(quociente) * relativa

    return np.sqrt(u_quociente ** 2 + u_r_cabos ** 2)


def derivadas_temperatura(temperatura_k, r0: float, alpha: float, beta: float) -> dict:
    """
    Derivadas parciais analíticas de T em relação a R, R0, α e β.

    Partindo de R = R0·(1 + α·Tc + β·Tc²) e derivando implicitamente, com
    Tc em °C (a derivada em kelvin é idêntica, pois diferem por constante).

    Denominador comum, que é dR/dTc:

        D = R0·(α + 2β·Tc)

        ∂T/∂R  = 1 / D                                                  (E9)
        ∂T/∂R0 = −(R/R0) / D   =  −(1 + α·Tc + β·Tc²) / D              (E10)
        ∂T/∂α  = −R0·Tc  / D                                            (E11)
        ∂T/∂β  = −R0·Tc² / D                                            (E12)

    Quando D → 0 o modelo perde sensibilidade: a curva R(T) fica horizontal e
    a inversão deixa de ser bem posta. Nesse caso devolvemos infinito, para que
    o ponto apareça com incerteza enorme em vez de passar despercebido.
    """
    tc = np.asarray(temperatura_k, dtype=float) - 273.15
    denominador = r0 * (alpha + 2.0 * beta * tc)

    with np.errstate(divide="ignore", invalid="ignore"):
        d_dr = np.where(denominador != 0, 1.0 / denominador, np.inf)
        d_dr0 = np.where(denominador != 0,
                         -(1 + alpha * tc + beta * tc ** 2) / denominador, np.inf)
        d_dalpha = np.where(denominador != 0, -r0 * tc / denominador, np.inf)
        d_dbeta = np.where(denominador != 0, -r0 * tc ** 2 / denominador, np.inf)

    return {"R": d_dr, "R0": d_dr0, "alpha": d_dalpha, "beta": d_dbeta}


def incerteza_temperatura(temperatura_k, u_resistencia_valor,
                          r0: float, alpha: float, beta: float,
                          u_r0: float = 0.0, u_alpha: float = 0.0,
                          u_beta: float = 0.0) -> tuple:
    """
    Incerteza da temperatura e o orçamento de cada fonte.

    Aplicação direta de (E4) com as derivadas (E9)–(E12):

        u_T² = (∂T/∂R)²u_R² + (∂T/∂R0)²u_R0² + (∂T/∂α)²u_α² + (∂T/∂β)²u_β²

    Devolve (u_T, contribuicoes), onde `contribuicoes` traz a VARIÂNCIA de cada
    termo — somá-las devolve u_T², e a razão de cada uma pelo total é a fatia
    daquela fonte no orçamento.
    """
    d = derivadas_temperatura(temperatura_k, r0, alpha, beta)

    contribuicoes = {
        "R": (d["R"] * np.asarray(u_resistencia_valor)) ** 2,
        "R0": (d["R0"] * u_r0) ** 2,
        "alpha": (d["alpha"] * u_alpha) ** 2,
        "beta": (d["beta"] * u_beta) ** 2,
    }
    variancia = sum(contribuicoes.values())
    return np.sqrt(variancia), contribuicoes


def incerteza_r0_corrigido(r_frio: float, t_ambiente_c: float,
                           alpha: float, beta: float,
                           u_r_frio: float = 0.0,
                           u_t_ambiente: float = INCERTEZA_TEMPERATURA_AMBIENTE) -> float:
    """
    Incerteza de R0 = R_frio / (1 + α·T_amb + β·T_amb²)  — a correção A2.

    Chamando o denominador de F:

        ∂R0/∂R_frio = 1/F
        ∂R0/∂T_amb  = −R_frio·(α + 2β·T_amb) / F²

    e aplicando (E4). A incerteza da temperatura ambiente importa mais do que
    parece: ela multiplica o coeficiente térmico inteiro.
    """
    f = 1 + alpha * t_ambiente_c + beta * t_ambiente_c ** 2
    if f <= 0:
        raise ValueError("Fator de correção de R0 não positivo.")

    d_dr = 1.0 / f
    d_dt = -r_frio * (alpha + 2 * beta * t_ambiente_c) / (f ** 2)

    return math.hypot(d_dr * u_r_frio, d_dt * u_t_ambiente)


# =============================================================================
# Ajuste linear ponderado
# =============================================================================

@dataclass
class AjusteLinear:
    """Resultado de um ajuste y = m·x + c com incertezas."""
    m: float
    u_m: float
    c: float
    u_c: float
    r2: float
    chi2_reduzido: float
    n_pontos: int
    iteracoes: int
    pesos: np.ndarray = field(repr=False, default=None)


def ajuste_linear_ponderado(x, y, u_y, u_x=None, max_iteracoes: int = 50,
                            tolerancia: float = 1e-12) -> AjusteLinear:
    """
    Mínimos quadrados ponderados, com opção de erro também em x.

    -- Caso só com erro em y (WLS clássico) --

    Peso de cada ponto é o inverso da variância — quem mede melhor pesa mais:

        w_i = 1 / u_yi²                                                 (E15)

    Minimizando χ² = Σ w_i (y_i − m·x_i − c)² chega-se às somas:

        S = Σw,  Sx = Σw·x,  Sy = Σw·y,  Sxx = Σw·x²,  Sxy = Σw·x·y
        Δ = S·Sxx − Sx²                                                 (E16)
        m = (S·Sxy − Sx·Sy) / Δ                                         (E17)
        c = (Sxx·Sy − Sx·Sxy) / Δ                                       (E18)
        u_m² = S / Δ                                                    (E19)
        u_c² = Sxx / Δ                                                  (E20)

    -- Caso com erro em x também (variância efetiva) --

    Aqui u_x NÃO é desprezível: x = 1/T, e T carrega o erro de R. O método da
    variância efetiva (Orear 1982; equivalente ao de York 1968 para retas)
    projeta o erro de x sobre y pela própria inclinação:

        w_i = 1 / (u_yi² + m²·u_xi²)

    Como o peso depende de m, itera-se: parte-se de m do WLS puro, recalculam-
    se os pesos, reajusta-se, até m estabilizar. Converge em poucas iterações.

    Preferido a uma rotina de ODR pronta por três razões: não acrescenta
    dependência (a `scipy.odr` está deprecada e sai na 1.19), o método cabe em
    vinte linhas auditáveis, e é citável.

    -- Diagnóstico --

    χ²_reduzido = χ²/(N−2) responde "as incertezas declaradas explicam a
    dispersão observada?". Perto de 1, sim. Muito acima, ou o modelo não serve
    ou as incertezas estão subestimadas. Muito abaixo, estão superestimadas.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    u_y = np.asarray(u_y, dtype=float)

    if x.size < 3:
        raise ValueError("São necessários ao menos 3 pontos para ajustar e diagnosticar.")
    if np.any(u_y <= 0):
        raise ValueError("Incertezas em y devem ser todas positivas.")

    def resolver(pesos):
        s = np.sum(pesos)
        sx = np.sum(pesos * x)
        sy = np.sum(pesos * y)
        sxx = np.sum(pesos * x * x)
        sxy = np.sum(pesos * x * y)
        delta = s * sxx - sx * sx
        if delta == 0:
            raise ValueError("Ajuste indeterminado: todos os x são iguais.")
        m = (s * sxy - sx * sy) / delta
        c = (sxx * sy - sx * sxy) / delta
        return m, c, math.sqrt(s / delta), math.sqrt(sxx / delta)

    pesos = 1.0 / u_y ** 2
    m, c, u_m, u_c = resolver(pesos)
    iteracoes = 0

    if u_x is not None:
        u_x = np.asarray(u_x, dtype=float)
        for iteracoes in range(1, max_iteracoes + 1):
            pesos = 1.0 / (u_y ** 2 + (m * u_x) ** 2)
            m_novo, c, u_m, u_c = resolver(pesos)
            if abs(m_novo - m) <= tolerancia * max(abs(m), 1e-300):
                m = m_novo
                break
            m = m_novo

    residuos = y - (m * x + c)
    chi2 = float(np.sum(pesos * residuos ** 2))
    graus_liberdade = x.size - 2

    media_ponderada = np.sum(pesos * y) / np.sum(pesos)
    ss_tot = float(np.sum(pesos * (y - media_ponderada) ** 2))
    r2 = 1.0 - chi2 / ss_tot if ss_tot > 0 else 0.0

    return AjusteLinear(
        m=m, u_m=u_m, c=c, u_c=u_c, r2=r2,
        chi2_reduzido=chi2 / graus_liberdade if graus_liberdade > 0 else float("nan"),
        n_pontos=int(x.size), iteracoes=iteracoes, pesos=pesos,
    )


# =============================================================================
# De volta a h
# =============================================================================

def incerteza_h(m: float, u_m: float, lambda_nm: float, u_lambda_nm: float) -> tuple:
    """
    Incerteza de h = −m·λ·k_B/c, equação (E21).

    Produto de fatores independentes: as incertezas relativas somam em
    quadratura (k_B e c são exatos por definição no SI atual, então não
    contribuem):

        (u_h/h)² = (u_m/m)² + (u_λ/λ)²                                  (E22)

    Devolve (u_h, contribuições relativas ao quadrado), para o orçamento.
    """
    if m == 0:
        raise ValueError("Inclinação nula: h indefinido.")

    h = -(m * (lambda_nm * 1e-9) * K_B) / C

    rel_m = (u_m / m) ** 2
    rel_lambda = (u_lambda_nm / lambda_nm) ** 2
    u_h = abs(h) * math.sqrt(rel_m + rel_lambda)

    return u_h, {"inclinacao": rel_m, "lambda": rel_lambda}


def incerteza_lambda(delta_lambda_nm: float,
                     divisor: float = DIVISOR_RETANGULAR) -> float:
    """
    Incerteza padrão do comprimento de onda a partir da largura espectral.

    O LED não responde a um único λ, e sim a uma banda de meia largura Δλ. Sem
    conhecer o formato exato da resposta espectral, tratamos a banda como
    retangular:

        u_λ = Δλ / √3

    Esta é, quase sempre, a MAIOR contribuição para a incerteza de h.
    """
    return delta_lambda_nm / divisor


def decompor_com_incerteza(valor: float, incerteza: float):
    """
    Separa "valor ± incerteza" em mantissa, incerteza e expoente já arredondados.

    Regra usual de metrologia: a incerteza expandida fica com 1 a 2 algarismos
    significativos, e o valor é arredondado na MESMA casa decimal. Reportar
    h = 6,6260701e-34 ± 2e-35 seria falso: os últimos dígitos não significam
    nada diante da incerteza.

    Devolve `(mantissa, mantissa_incerteza, expoente, casas)` ou `None` quando
    os números não permitem o arredondamento (não finitos, ou incerteza nula).
    Existe separada de `formatar_com_incerteza` porque a interface precisa das
    partes soltas — mostra o valor em corpo grande e a incerteza abaixo —, e a
    regra de arredondamento não pode ter duas implementações.
    """
    if not np.isfinite(valor) or not np.isfinite(incerteza) or incerteza <= 0:
        return None

    expoente = math.floor(math.log10(abs(valor))) if valor != 0 else 0
    mantissa = valor / (10 ** expoente)
    mantissa_u = incerteza / (10 ** expoente)

    # Casas decimais: o suficiente para dar 2 algarismos à incerteza.
    if mantissa_u > 0:
        casas = max(0, -int(math.floor(math.log10(mantissa_u))) + 1)
    else:
        casas = 2
    casas = min(casas, 8)
    return mantissa, mantissa_u, expoente, casas


def formatar_com_incerteza(valor: float, incerteza: float,
                           unidade: str = "", k: float = FATOR_ABRANGENCIA_PADRAO) -> str:
    """Formata "valor ± incerteza" numa linha só, para relatórios e logs."""
    partes = decompor_com_incerteza(valor, incerteza)
    if partes is None:
        return f"{valor:.4e} {unidade}".strip()
    mantissa, mantissa_u, expoente, casas = partes

    texto = f"({mantissa:.{casas}f} ± {mantissa_u:.{casas}f})×10^{expoente}"
    if unidade:
        texto += f" {unidade}"
    return f"{texto} (k={k:g})"


# =============================================================================
# A cadeia completa, num lugar só
# =============================================================================

@dataclass
class ResultadoAnalise:
    """Tudo que uma coleta produz, com incerteza e rastreabilidade."""

    h: float                    # J·s
    u_h: float                  # incerteza padrão combinada
    incerteza_expandida: float  # U = k·u_h
    k: float
    erro_relativo: float        # % contra a CODATA
    compativel_com_codata: bool # |h − h_ref| ≤ U ?

    ajuste: AjusteLinear
    n_usados: int
    n_total: int
    mascara: np.ndarray = field(repr=False, default=None)

    orcamento_h: dict = field(default_factory=dict)
    orcamento_temperatura: dict = field(default_factory=dict)

    h_nao_ponderado: float = float("nan")
    temperaturas: np.ndarray = field(repr=False, default=None)
    u_temperaturas: np.ndarray = field(repr=False, default=None)
    resistencias: np.ndarray = field(repr=False, default=None)

    @property
    def texto(self) -> str:
        return formatar_com_incerteza(self.h, self.incerteza_expandida, "J·s", self.k)

    def orcamento_ordenado(self) -> list:
        """Fontes de incerteza de h, da que mais contribui para a que menos."""
        total = sum(self.orcamento_h.values())
        if total <= 0:
            return []
        return sorted(((nome, valor / total * 100)
                       for nome, valor in self.orcamento_h.items()),
                      key=lambda par: par[1], reverse=True)


def analisar_experimento(tensao, corrente, fotocorrente, *,
                         r0: float, alpha: float, beta: float,
                         lambda_nm: float,
                         delta_lambda_nm: float = DELTA_LAMBDA_PADRAO_NM,
                         r_cabos: float = 0.0, u_r_cabos: float = 0.0,
                         u_r0: float = 0.0, u_alpha: float = 0.0, u_beta: float = 0.0,
                         u_fotocorrente_tipo_a=None,
                         t_minima: float = TEMPERATURA_MINIMA_PADRAO,
                         k: float = FATOR_ABRANGENCIA_PADRAO,
                         spec_tensao: EspecificacaoInstrumento = PWS4323_TENSAO_READBACK,
                         spec_corrente: EspecificacaoInstrumento = PWS4323_CORRENTE_READBACK,
                         spec_fotocorrente: EspecificacaoInstrumento = DMM4050_CORRENTE_100UA,
                         ) -> ResultadoAnalise:
    """
    Percorre a cadeia inteira, de medidas brutas a h ± U.

    Recebe os três vetores medidos — tensão nos terminais, corrente do
    filamento e fotocorrente do LED — e devolve o resultado com o orçamento de
    incertezas. Cada passo abaixo remete à equação correspondente no cabeçalho
    deste módulo.

    `u_fotocorrente_tipo_a` é opcional: quando o operador pede N leituras por
    ponto, entra aqui o s/√N de cada ponto, que se combina em quadratura com a
    incerteza de datasheet (E3). Sem ele, só há Tipo B.
    """
    tensao = np.asarray(tensao, dtype=float)
    corrente = np.asarray(corrente, dtype=float)
    fotocorrente = np.asarray(fotocorrente, dtype=float)

    # --- Passo 1: incerteza das medidas elétricas (Tipo B, E2) ---
    u_tensao = spec_tensao.incerteza_padrao(tensao)
    u_corrente = spec_corrente.incerteza_padrao(corrente)

    # --- Passo 2: resistência e sua incerteza (E8) ---
    with np.errstate(divide="ignore", invalid="ignore"):
        resistencias = tensao / corrente - r_cabos
    u_resistencias = incerteza_resistencia(tensao, corrente, u_tensao, u_corrente, u_r_cabos)

    # --- Passo 3: temperatura e sua incerteza ALEATÓRIA (E9–E12) ---
    # Só a parte que varia ponto a ponto — vinda de u_R — entra aqui. R0, α e
    # β são sistemáticos e são tratados no passo 9 (ver H3b no cabeçalho).
    temperaturas = calculate_temperature(resistencias, r0, alpha, beta)
    u_temperaturas, contrib_t = incerteza_temperatura(
        temperaturas, u_resistencias, r0, alpha, beta,
        u_r0=0.0, u_alpha=0.0, u_beta=0.0)

    # Orçamento informativo da temperatura: aqui sim com tudo, para mostrar ao
    # operador quem pesa mais na incerteza de T (não é usado na ponderação).
    _, contrib_t_total = incerteza_temperatura(
        temperaturas, u_resistencias, r0, alpha, beta, u_r0, u_alpha, u_beta)

    # --- Passo 4: incerteza da fotocorrente (Tipo B ⊕ Tipo A, E3) ---
    u_foto = spec_fotocorrente.incerteza_padrao(fotocorrente)
    if u_fotocorrente_tipo_a is not None:
        u_foto = np.sqrt(u_foto ** 2 + np.asarray(u_fotocorrente_tipo_a, dtype=float) ** 2)

    # --- Passo 5: quais pontos entram (A5 + B6) ---
    limiar = limiar_corrente_confiavel(spec_fotocorrente)
    mascara = selecionar_pontos_validos(temperaturas, fotocorrente,
                                        t_minima=t_minima, limiar_corrente=limiar)
    # Uma temperatura sem incerteza finita não é utilizável na ponderação.
    mascara = mascara & np.isfinite(u_temperaturas) & (u_temperaturas > 0)

    n_total = int(tensao.size)
    n_usados = int(np.sum(mascara))
    if n_usados < 3:
        raise ValueError(
            f"Apenas {n_usados} ponto(s) sobreviveram aos critérios de seleção; "
            "são necessários ao menos 3 para ajustar e diagnosticar."
        )

    # --- Passo 6: linearização e propagação para os eixos (E13, E14) ---
    t_validos = temperaturas[mascara]
    x = 1.0 / t_validos
    u_x = u_temperaturas[mascara] / t_validos ** 2          # (E13)
    y = np.log(fotocorrente[mascara])
    u_y = u_foto[mascara] / fotocorrente[mascara]           # (E14)

    # --- Passo 7: ajuste ponderado com erro nos dois eixos (E15–E20) ---
    ajuste = ajuste_linear_ponderado(x, y, u_y, u_x)

    # Referência didática: o mesmo ajuste sem ponderar, para comparação.
    coef_simples = np.polyfit(x, y, 1)
    h_simples = -(coef_simples[0] * lambda_nm * 1e-9 * K_B) / C

    # --- Passo 8: h a partir da inclinação (E21) ---
    fator_h = -(lambda_nm * 1e-9 * K_B) / C
    h = fator_h * ajuste.m

    # --- Passo 9: contribuições SISTEMÁTICAS, por sensibilidade (H3b) ---
    #
    # Para cada parâmetro comum a toda a varredura, desloca-se de +u, refaz-se
    # a cadeia com a MESMA seleção de pontos (queremos a sensibilidade do
    # resultado ao parâmetro, não à seleção) e mede-se o quanto h anda.
    def _h_com_parametros(r0_alt, alpha_alt, beta_alt):
        t_alt = calculate_temperature(resistencias, r0_alt, alpha_alt, beta_alt)
        t_sel = t_alt[mascara]
        if not np.all(np.isfinite(t_sel)) or np.any(t_sel <= 0):
            return None
        u_t_alt, _ = incerteza_temperatura(t_alt, u_resistencias,
                                           r0_alt, alpha_alt, beta_alt)
        try:
            ajuste_alt = ajuste_linear_ponderado(
                1.0 / t_sel, y, u_y, u_t_alt[mascara] / t_sel ** 2)
        except ValueError:
            return None
        return fator_h * ajuste_alt.m

    sistematicas = {}
    for nome, u_valor, argumentos in (
        ("R0", u_r0, (r0 + u_r0, alpha, beta)),
        ("alpha", u_alpha, (r0, alpha + u_alpha, beta)),
        ("beta", u_beta, (r0, alpha, beta + u_beta)),
    ):
        if u_valor and u_valor > 0:
            h_deslocado = _h_com_parametros(*argumentos)
            if h_deslocado is not None:
                sistematicas[nome] = (h_deslocado - h) ** 2

    # --- Passo 10: combinação final (E22 + sistemáticas) ---
    u_lambda = incerteza_lambda(delta_lambda_nm)
    variancia_ajuste = (ajuste.u_m / ajuste.m) ** 2 * h ** 2 if ajuste.m else 0.0
    variancia_lambda = (u_lambda / lambda_nm) ** 2 * h ** 2

    orcamento = {"inclinacao (aleatório)": variancia_ajuste,
                 "lambda": variancia_lambda}
    orcamento.update(sistematicas)

    u_h = math.sqrt(sum(orcamento.values()))
    incerteza_expandida = k * u_h                            # (E5)

    # Orçamento da temperatura: mediana da fatia de cada fonte nos pontos usados.
    contrib_t = contrib_t_total
    total_t = sum(contrib_t.values())
    orcamento_t = {}
    with np.errstate(divide="ignore", invalid="ignore"):
        for nome, valor in contrib_t.items():
            fatia = np.where(total_t > 0, valor / total_t, 0.0)[mascara]
            finitos = fatia[np.isfinite(fatia)]
            orcamento_t[nome] = float(np.median(finitos) * 100) if finitos.size else 0.0

    return ResultadoAnalise(
        h=h, u_h=u_h, incerteza_expandida=incerteza_expandida, k=k,
        erro_relativo=abs(h - H_REF) / H_REF * 100,
        compativel_com_codata=abs(h - H_REF) <= incerteza_expandida,
        ajuste=ajuste, n_usados=n_usados, n_total=n_total, mascara=mascara,
        orcamento_h=orcamento, orcamento_temperatura=orcamento_t,
        h_nao_ponderado=h_simples,
        temperaturas=temperaturas, u_temperaturas=u_temperaturas,
        resistencias=resistencias,
    )
