# utils/math_models.py
import numpy as np

# Constantes Físicas Fundamentais (CODATA)
C = 299792458.0              # Velocidade da luz (m/s)
K_B = 1.380649e-23           # Constante de Boltzmann (J/K)
H_REF = 6.62607015e-34       # Constante de Planck de referência (J.s)
E_CHARGE = 1.602176634e-19   # Carga elementar (C)

TEMPERATURA_AMBIENTE_PADRAO = 25.0   # °C
TEMPERATURA_MINIMA_PADRAO = 1800.0   # K — piso da região de Wien útil (ver A5)
TEMPERATURA_AMBIENTE_K = 298.15      # K (25 °C) — ambiente do balanço de energia

# --- Balanço de energia do filamento (Eq. 9 do artigo + condução) -----------
#
# Em regime estacionário, a potência elétrica entregue ao filamento é toda
# dissipada:
#
#     V²/R(T) = k_rad·(T⁴ − T_amb⁴) + k_cond·(T − T_amb)
#
# O primeiro termo é a radiação (Stefan-Boltzmann, ε·σ·A agrupados em k_rad);
# o segundo, a condução pelos terminais. É esta equação que liga a tensão
# aplicada à temperatura — a relação V→T que o experimento de fato mede.
#
# Os números abaixo NÃO foram inventados: saem de um ajuste de mínimos
# quadrados sobre os 1127 pontos úteis dos 52 CSVs reais de `data_backup/`
# (resíduo mediano de 2,9% em potência), refeito por
# `Tests/calibrar_mock_com_dados_reais.py`. O que o ajuste fixa é a RAZÃO
# k_cond/k_rad — a forma da curva —; a escala é recalibrada por
# `calibrar_dissipacao` para o filamento em uso bater a âncora medida na
# bancada real: 2540 K a 12 V.
RAZAO_COND_RAD = 1.32760e8   # k_cond/k_rad, em K³
ANCORA_TENSAO = 12.0         # V — topo da varredura real
ANCORA_TEMPERATURA = 2540.0  # K — temperatura medida nesse topo
ANCORA_FOTOCORRENTE = 7.2e-7 # A — fotocorrente do LED de 590 nm nesse ponto

# Menor fotocorrente que ainda carrega informação, em ampères (B6).
#
# NÃO é um número escolhido à mão: é o resultado de
# `error_models.limiar_corrente_confiavel()`, que exige que a leitura supere a
# margem de exatidão do próprio DMM4050 na faixa de 100 µA. Fica replicado aqui
# como constante para não criar import circular (error_models importa este
# módulo); `Tests/test_error_models.py` verifica que os dois valores concordam.
#
# O valor antigo era 1e-9 (1 nA) — menor que o ruído de fundo do instrumento,
# de modo que não descartava ponto nenhum.
LIMIAR_CORRENTE_PADRAO = 25e-9


def corrigir_r0_para_zero_celsius(r_frio: float, t_ambiente_c: float,
                                  alpha: float, beta: float) -> float:
    """
    Converte a resistência medida a frio em R0, a resistência a 0 °C (Eq. 11).

    O modelo R(Tc) = R0·(1 + α·Tc + β·Tc²) define R0 como a resistência a
    **0 °C**. Mas o operador mede o filamento frio na temperatura **ambiente**,
    tipicamente 25 °C, onde a resistência já é ~13% maior. Usar a medida
    direto como R0 enviesa todas as temperaturas — e portanto h.

    Invertendo o modelo na temperatura ambiente:

        R0 = R(T_amb) / (1 + α·T_amb + β·T_amb²)
    """
    divisor = 1 + alpha * t_ambiente_c + beta * t_ambiente_c**2
    if divisor <= 0:
        raise ValueError(
            "Coeficientes inválidos: o fator de correção de R0 ficou não positivo "
            f"({divisor:.4g}) para T_amb = {t_ambiente_c} °C."
        )
    return r_frio / divisor


def calculate_temperature(R_array: np.ndarray, R0: float, alpha: float, beta: float) -> np.ndarray:
    """
    Calcula a temperatura (K) do filamento a partir da sua resistência.
    Resolve a equação quadrática: R(T) = R0 * (1 + alpha*T + beta*T^2)
    Utiliza a fórmula de Bhaskara para encontrar a raiz física (positiva).

    R0 aqui é a resistência a 0 °C — se você tem a medida a frio na temperatura
    ambiente, passe-a antes por `corrigir_r0_para_zero_celsius`.

    Resistências que não têm solução real (discriminante negativo, o que
    acontece quando R medido fica abaixo do mínimo do polinômio) devolvem NaN
    em vez de lixo: o ponto é fisicamente impossível e deve ser descartado,
    não usado.
    """
    R_array = np.asarray(R_array, dtype=float)

    # R0*beta*T^2 + R0*alpha*T + (R0 - R) = 0
    a = R0 * beta
    b = R0 * alpha
    c = R0 - R_array

    # Sem termo quadrático a equação degenera para uma reta; resolver por
    # Bhaskara dividiria por zero.
    if a == 0:
        if b == 0:
            return np.full_like(R_array, np.nan)
        return (-c / b) + 273.15

    delta = b**2 - 4 * a * c
    delta_segura = np.where(delta >= 0, delta, np.nan)

    # Apenas a raiz que faz sentido físico (T > 0 e crescente com R)
    T_celsius = (-b + np.sqrt(delta_segura)) / (2 * a)
    T_kelvin = T_celsius + 273.15
    return T_kelvin

def resistencia_do_filamento(T_kelvin, R0: float, alpha: float, beta: float):
    """R(T) = R0·(1 + α·Tc + β·Tc²), com Tc em °C. Aceita escalar ou vetor."""
    tc = np.asarray(T_kelvin, dtype=float) - 273.15
    return R0 * (1 + alpha * tc + beta * tc**2)


def resolver_temperatura_regime(tensao: float, R0: float, alpha: float, beta: float,
                                k_rad: float, k_cond: float,
                                t_ambiente_k: float = TEMPERATURA_AMBIENTE_K) -> float:
    """
    Temperatura de regime para uma tensão aplicada, por bissecção.

    Resolve V²/R(T) = k_rad·(T⁴ − T_amb⁴) + k_cond·(T − T_amb). O desequilíbrio
    (potência entregue − potência dissipada) é monótono decrescente em T, então
    a bissecção é segura e não precisa de derivada.

    É a MESMA função usada pela bancada simulada (`core/mock_hardware.py`) e
    pela simulação (`simulate_experiment_data`): um único lugar para a relação
    V→T, para os dois nunca divergirem.
    """
    if tensao <= 0:
        return t_ambiente_k

    def desequilibrio(t):
        return tensao**2 / resistencia_do_filamento(t, R0, alpha, beta) - (
            k_rad * (t**4 - t_ambiente_k**4) + k_cond * (t - t_ambiente_k)
        )

    baixo, alto = t_ambiente_k, 4000.0
    if desequilibrio(baixo) <= 0:
        return t_ambiente_k
    for _ in range(120):
        meio = 0.5 * (baixo + alto)
        if desequilibrio(meio) > 0:
            baixo = meio
        else:
            alto = meio
    return 0.5 * (baixo + alto)


def calibrar_dissipacao(R0: float, alpha: float, beta: float,
                        razao_cond_rad: float = RAZAO_COND_RAD,
                        ancora_tensao: float = ANCORA_TENSAO,
                        ancora_temperatura: float = ANCORA_TEMPERATURA) -> tuple:
    """
    Escala (k_rad, k_cond) para o filamento dado bater a âncora da bancada real.

    A razão k_cond/k_rad vem do ajuste sobre os CSVs reais; o que falta é a
    escala absoluta, que depende da geometria do filamento (ε·σ·A). Em vez de
    chutá-la, fixa-se o ponto medido: `ancora_tensao` → `ancora_temperatura`.
    Bissecção em k_rad porque T(12 V) é monótona decrescente em k_rad.
    """
    baixo, alto = 1e-16, 1e-9
    for _ in range(200):
        k_rad = 0.5 * (baixo + alto)
        k_cond = k_rad * razao_cond_rad
        t = resolver_temperatura_regime(ancora_tensao, R0, alpha, beta, k_rad, k_cond)
        if t > ancora_temperatura:
            baixo = k_rad   # dissipa pouco demais, esquenta demais
        else:
            alto = k_rad
    k_rad = 0.5 * (baixo + alto)
    return k_rad, k_rad * razao_cond_rad


def simulate_experiment_data(voltages: np.ndarray, R0: float, alpha: float, beta: float,
                             lambda_led_nm: float, noise_level: float = 0.05,
                             fuga_dmm: float = 4.5e-9,
                             semente: int | None = None) -> tuple:
    """
    Gera uma varredura sintética com a física do experimento real (A9).

    A versão antiga impunha T = linspace(1500, 3000) INDEPENDENTE das tensões:
    o primeiro ponto de uma varredura 0–12 V já "estava" a 1500 K, e a relação
    V→T — que é o coração do experimento — simplesmente não existia. Qualquer
    conclusão tirada da simulação sobre faixa de varredura era fantasia.

    Agora cada tensão passa pelo balanço de energia (`resolver_temperatura_regime`)
    com a dissipação calibrada nos dados reais, e TUDO deriva daí:

        V → T (balanço de energia) → R(T) → i = V/R → I_led (Wien, com o h da
        CODATA embutido)

    O h de referência está DENTRO dos dados gerados; recuperá-lo pela regressão
    é o teste de coerência de toda a cadeia de análise.

    Dois artefatos do instrumento real são reproduzidos de propósito:

    - `fuga_dmm`: o fundo de ~4,5 nA que os CSVs reais mostram em tensão baixa.
      Com ele, a simulação exibe o mesmo fenômeno da bancada — pontos frios que
      não são sinal e precisam ser cortados pela região de Wien — em vez de
      esconder o problema que a seleção de pontos existe para resolver.
    - `noise_level`: ruído proporcional ao sinal, controlado pelo operador.

    `semente` congela o gerador para testes reprodutíveis. Retorna
    (tensões, corrente do filamento, resistência, temperatura, fotocorrente).
    """
    voltages = np.asarray(voltages, dtype=float)
    rng = np.random.default_rng(semente)

    k_rad, k_cond = calibrar_dissipacao(R0, alpha, beta)
    T_kelvin = np.array([
        resolver_temperatura_regime(v, R0, alpha, beta, k_rad, k_cond)
        for v in voltages
    ])

    R_filament = resistencia_do_filamento(T_kelvin, R0, alpha, beta)
    current_filament = voltages / R_filament

    # Wien ancorado no ponto medido da bancada real, como no mock: a escala
    # absoluta do LED não importa para h (só a inclinação de ln I × 1/T), mas
    # ancorá-la mantém os números na ordem de grandeza dos CSVs reais.
    lambda_led = lambda_led_nm * 1e-9
    expoente = -(H_REF * C) / (lambda_led * K_B * T_kelvin)
    expoente_ancora = -(H_REF * C) / (lambda_led * K_B * ANCORA_TEMPERATURA)
    fator_led = ANCORA_FOTOCORRENTE / np.exp(expoente_ancora)
    ideal_photocurrent = np.where(
        T_kelvin > TEMPERATURA_AMBIENTE_K,
        fator_led * np.exp(np.maximum(expoente, -700.0)),   # evita underflow
        0.0,
    )

    ruido = rng.normal(0.0, 1.0, size=len(voltages)) * (noise_level * ideal_photocurrent)
    noisy_photocurrent = ideal_photocurrent + fuga_dmm + ruido

    # O DMM não lê negativo nesta aplicação; o piso é a própria resolução.
    noisy_photocurrent = np.clip(noisy_photocurrent, a_min=1e-10, a_max=None)

    return voltages, current_filament, R_filament, T_kelvin, noisy_photocurrent

def selecionar_pontos_validos(T_kelvin: np.ndarray, photocurrent: np.ndarray,
                              t_minima: float = 0.0,
                              limiar_corrente: float = LIMIAR_CORRENTE_PADRAO) -> np.ndarray:
    """
    Máscara booleana dos pontos que podem entrar na regressão.

    Três critérios, nesta ordem:

    1. **Temperatura fisicamente possível** — descarta NaN (discriminante
       negativo na Bhaskara) e qualquer T ≤ 0. Atenção: a Bhaskara devolve
       raízes matematicamente válidas e fisicamente absurdas quando a
       resistência medida fica abaixo de R0 — é a origem dos T ≈ 77 K no
       início das varreduras reais, e de temperaturas negativas em casos
       extremos. Uma temperatura absoluta não positiva não é uma medida ruim,
       é uma impossibilidade, e não pode entrar no 1/T.
    2. **Região de Wien** (`t_minima`) — abaixo de ~1800 K a fotocorrente é
       ordens de grandeza menor que o fundo do multímetro; o que se lê ali não
       é sinal, é piso instrumental. Incluir esses pontos não só não ajuda como
       envenena a reta, porque eles entram como se fossem medidas legítimas.
       Este é o critério que permite varrer a faixa inteira (inclusive de 0 V)
       sem estragar o resultado: varre-se tudo, regride-se só o que informa.
    3. **Fotocorrente acima do limiar** — mantém o log finito.

    A UI usa esta mesma máscara para pintar de cinza os pontos descartados, de
    modo que o operador veja o que entrou e o que não entrou na conta.
    """
    T_kelvin = np.asarray(T_kelvin, dtype=float)
    photocurrent = np.asarray(photocurrent, dtype=float)

    temperatura_utilizavel = np.isfinite(T_kelvin) & (T_kelvin > 0)
    regiao_de_wien = T_kelvin >= t_minima
    sinal_acima_do_piso = np.isfinite(photocurrent) & (photocurrent > limiar_corrente)

    return temperatura_utilizavel & regiao_de_wien & sinal_acima_do_piso


def calculate_planck_constant(T_kelvin: np.ndarray, photocurrent: np.ndarray,
                              lambda_led_nm: float,
                              t_minima: float = 0.0,
                              limiar_corrente: float = LIMIAR_CORRENTE_PADRAO) -> tuple:
    """
    Realiza a regressão linear de ln(I) vs 1/T para extrair a constante de Planck experimental.

    `t_minima` recorta a região de Wien (ver `selecionar_pontos_validos`). O
    padrão 0.0 mantém o comportamento antigo — quem chama decide o corte.

    Retorna: (h_experimental, erro_relativo, coef_angular, coef_linear, r_squared)
    """
    lambda_led = lambda_led_nm * 1e-9
    T_kelvin = np.asarray(T_kelvin, dtype=float)
    photocurrent = np.asarray(photocurrent, dtype=float)

    valid_indices = selecionar_pontos_validos(
        T_kelvin, photocurrent, t_minima, limiar_corrente
    )

    x_valid = 1 / T_kelvin[valid_indices]
    y_valid = np.log(photocurrent[valid_indices])

    if len(x_valid) < 2:
        return 0, 0, 0, 0, 0

    A = np.vstack([x_valid, np.ones(len(x_valid))]).T
    m, c = np.linalg.lstsq(A, y_valid, rcond=None)[0]

    y_pred = m * x_valid + c
    ss_res = np.sum((y_valid - y_pred)**2)
    ss_tot = np.sum((y_valid - np.mean(y_valid))**2)
    # Guard (B9): ss_tot = 0 quando todos os ln(I) são iguais (reta horizontal,
    # ou um único valor repetido). O R² é indefinido nesse caso; reportamos 0.0
    # em vez de deixar o NaN/inf da divisão por zero chegar à UI e ao PDF.
    r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

    h_experimental = - (m * lambda_led * K_B) / C
    erro_relativo = abs(h_experimental - H_REF) / H_REF * 100
    
    return h_experimental, erro_relativo, m, c, r_squared