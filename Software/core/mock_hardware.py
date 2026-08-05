# core/mock_hardware.py
"""
Bancada simulada — drivers falsos com a MESMA interface dos reais.

Serve para desenvolver e testar sem a fonte e o multímetro ligados. Os mocks
são substituíveis um a um pelos drivers reais: `MockPWS4323_Driver` expõe os
mesmos métodos de `PWS4323_Driver`, e `MockDMM4050_Driver` os de
`DMM4050_Driver`, inclusive a assinatura `(resource_manager, resource_string)`.

Como a física foi calibrada
---------------------------
Os dois instrumentos reais são acoplados pelo filamento: a tensão que a fonte
aplica define a temperatura, e é a temperatura que o LED enxerga. Por isso os
dois mocks compartilham um objeto `BancadaSimulada`.

O filamento resolve o balanço de energia em regime estacionário (Eq. 9 do
artigo, com um termo de condução somado):

    V²/R(T) = k_rad·(T⁴ − T_amb⁴) + k_cond·(T − T_amb)
    R(T)    = R0·(1 + a·Tc + b·Tc²)

`k_rad` e `k_cond` NÃO foram inventados: saíram de um ajuste de mínimos
quadrados sobre os 1127 pontos úteis dos 52 CSVs reais em `data_backup/`
(resíduo mediano de 2,9% em potência; a 2500 K a radiação responde por 99%
dela). O que se preserva daquele ajuste é a razão k_cond/k_rad — a "forma" da
curva —, e a escala é recalibrada no __init__ para que o filamento virtual
chegue a 2540 K em 12 V, que é o topo medido na bancada real.

A fotocorrente do LED segue a aproximação de Wien com o h de referência
(CODATA). É o ponto central do mock: os dados que ele gera *contêm* o valor
verdadeiro de h, então a regressão do software tem de conseguir recuperá-lo.

O que este mock reproduz de propósito (e que ainda não está corrigido)
---------------------------------------------------------------------
- **Piso do DMM.** Abaixo de ~1500 K a fotocorrente real cai para muito menos
  que o ruído do multímetro, e o que se lê é fundo de escala, não sinal. Os
  CSVs reais mostram exatamente isso (~4 nA em V baixo). O mock reproduz esse
  piso, então os pontos frios continuam poluindo a regressão enquanto B6/A5
  não forem corrigidos (Fases 2 e 3). Isso é intencional: sem o defeito no
  mock, não há como verificar a correção.
- **Erro de setting da fonte.** `set_voltage` guarda um valor com o erro de
  programação; `measure_voltage` devolve o valor com o erro (menor) de
  readback. É a diferença que motiva A4.

O que este mock ainda NÃO reproduz: inércia térmica (o filamento vai direto
ao regime estacionário — os workers já esperam o tempo de estabilização), e a
resistência dos cabos da medição a 2 fios.
"""
import math
import random

from utils.math_models import C, K_B, H_REF

# --- Constantes da bancada virtual -------------------------------------------

T_AMBIENTE = 298.15          # K (25 °C)

# Razão k_cond/k_rad do ajuste sobre os CSVs reais (unidade: K³).
RAZAO_COND_RAD = 1.32754e8

# Âncora de calibração: topo medido na bancada real.
ANCORA_TENSAO = 12.0         # V
ANCORA_TEMPERATURA = 2540.0  # K
ANCORA_FOTOCORRENTE = 7.2e-7 # A, lida pelo LED de 590 nm a 2540 K

# Exatidão dos instrumentos (datasheets — ver aba Referências).
PWS_SETTING_PCT, PWS_SETTING_FIXO = 0.0005, 10e-3   # ±(0,05% + 10 mV)
PWS_READBACK_V_PCT, PWS_READBACK_V_FIXO = 0.0002, 3e-3    # ±(0,02% + 3 mV)
PWS_READBACK_I_PCT, PWS_READBACK_I_FIXO = 0.0005, 2e-3    # ±(0,05% + 2 mA)
DMM_LEITURA_PCT = 0.0005                             # 0,05% da leitura
DMM_RESOLUCAO = 100e-12                              # 100 pA (6½ dígitos)

# Fundo do multímetro observado nos CSVs reais em tensão baixa.
DMM_FUGA = 4.5e-9            # A, offset sistemático
DMM_RUIDO = 2.0e-9           # A, desvio padrão do ruído de zero

STRING_RECURSO_PWS = "DEMO::PWS4323::SIMULADO"
STRING_RECURSO_DMM = "DEMO::DMM4050::SIMULADO"


class BancadaSimulada:
    """Filamento + LED virtuais, compartilhados pelos dois drivers mock."""

    def __init__(self, r0: float = 1.2, alpha: float = 5.23e-3,
                 beta: float = 7.0e-7, lambda_led_nm: float = 590.0,
                 semente: int | None = None):
        self.r0 = r0
        self.alpha = alpha
        self.beta = beta
        self.lambda_led = lambda_led_nm * 1e-9
        self._rng = random.Random(semente)

        # Estado da fonte
        self.saida_ligada = False
        self.tensao_programada = 0.0
        self._tensao_real = 0.0
        self.limite_corrente = 1.0

        self._calibrar()

    # --- calibração ----------------------------------------------------------

    def _calibrar(self):
        """Escala k_rad/k_cond para o filamento bater a âncora da bancada real."""
        alvo, baixo, alto = ANCORA_TEMPERATURA, 1e-16, 1e-9
        for _ in range(200):
            self.k_rad = 0.5 * (baixo + alto)
            self.k_cond = self.k_rad * RAZAO_COND_RAD
            if self._resolver_temperatura(ANCORA_TENSAO) > alvo:
                baixo = self.k_rad   # dissipa pouco demais, esquenta demais
            else:
                alto = self.k_rad
        self.k_rad = 0.5 * (baixo + alto)
        self.k_cond = self.k_rad * RAZAO_COND_RAD

        # Constante do LED: fixa a fotocorrente na âncora (Wien com o h real).
        self._fator_led = ANCORA_FOTOCORRENTE / math.exp(
            self._expoente_wien(ANCORA_TEMPERATURA)
        )

    def _expoente_wien(self, temperatura: float) -> float:
        return -(H_REF * C) / (self.lambda_led * K_B * temperatura)

    # --- física --------------------------------------------------------------

    def resistencia(self, temperatura: float) -> float:
        tc = temperatura - 273.15
        return self.r0 * (1 + self.alpha * tc + self.beta * tc**2)

    def resistencia_a_frio(self, t_ambiente_celsius: float) -> float:
        """
        O que um ohmímetro leria no filamento virtual em repouso.

        `self.r0` é a resistência a 0 °C, que é a definição do modelo. O
        operador, porém, mede na temperatura ambiente — é este o número que ele
        deve digitar no campo "resistência a frio medida".
        """
        return self.r0 * (1 + self.alpha * t_ambiente_celsius
                          + self.beta * t_ambiente_celsius**2)

    def _resolver_temperatura(self, tensao: float) -> float:
        """
        T de regime para uma tensão aplicada, por bissecção no balanço de energia.

        A função potência_entregue − potência_dissipada é monótona decrescente
        em T, então a bissecção é segura e não precisa de derivada.
        """
        if tensao <= 0:
            return T_AMBIENTE

        def desequilibrio(t):
            return tensao**2 / self.resistencia(t) - (
                self.k_rad * (t**4 - T_AMBIENTE**4)
                + self.k_cond * (t - T_AMBIENTE)
            )

        baixo, alto = T_AMBIENTE, 4000.0
        if desequilibrio(baixo) <= 0:
            return T_AMBIENTE
        for _ in range(120):
            meio = 0.5 * (baixo + alto)
            if desequilibrio(meio) > 0:
                baixo = meio
            else:
                alto = meio
        return 0.5 * (baixo + alto)

    def _retangular(self, limite: float) -> float:
        """Sorteio numa distribuição retangular de meia-largura `limite`."""
        return self._rng.uniform(-limite, limite)

    # --- interface usada pelos drivers ---------------------------------------

    def aplicar_tensao(self, volts: float):
        """A fonte programa a tensão; o valor aplicado carrega o erro de setting."""
        self.tensao_programada = volts
        erro = self._retangular(PWS_SETTING_PCT * abs(volts) + PWS_SETTING_FIXO)
        self._tensao_real = max(0.0, volts + erro)

    def estado_eletrico(self) -> tuple:
        """(tensão nos terminais, corrente, temperatura) — valores verdadeiros."""
        if not self.saida_ligada or self._tensao_real <= 0:
            return 0.0, 0.0, T_AMBIENTE

        temperatura = self._resolver_temperatura(self._tensao_real)
        resistencia = self.resistencia(temperatura)
        corrente = self._tensao_real / resistencia

        # Modo corrente constante: a fonte segura a corrente e derruba a tensão.
        if corrente > self.limite_corrente:
            corrente = self.limite_corrente
            tensao = corrente * resistencia
            temperatura = self._resolver_temperatura(tensao)
            return tensao, corrente, temperatura

        return self._tensao_real, corrente, temperatura

    def ler_corrente_filamento(self) -> float:
        _, corrente, _ = self.estado_eletrico()
        if corrente <= 0:
            return abs(self._retangular(PWS_READBACK_I_FIXO))
        return corrente + self._retangular(
            PWS_READBACK_I_PCT * corrente + PWS_READBACK_I_FIXO
        )

    def ler_tensao_filamento(self) -> float:
        tensao, _, _ = self.estado_eletrico()
        if tensao <= 0:
            return abs(self._retangular(PWS_READBACK_V_FIXO))
        return tensao + self._retangular(
            PWS_READBACK_V_PCT * tensao + PWS_READBACK_V_FIXO
        )

    def ler_fotocorrente(self) -> float:
        """
        Fotocorrente do LED lida pelo DMM, com o piso instrumental real.

        Abaixo de ~1500 K o termo de Wien é ordens de grandeza menor que o
        fundo do multímetro — a leitura vira só fuga + ruído, como nos CSVs.
        """
        _, _, temperatura = self.estado_eletrico()

        if temperatura <= T_AMBIENTE:
            ideal = 0.0
        else:
            expoente = self._expoente_wien(temperatura)
            # exp(-750) e afins estouram em underflow; abaixo disso é zero mesmo.
            ideal = self._fator_led * math.exp(expoente) if expoente > -700 else 0.0

        ruido = self._rng.gauss(0.0, DMM_LEITURA_PCT * ideal / math.sqrt(3) + DMM_RUIDO)
        leitura = ideal + DMM_FUGA + ruido

        # O DMM entrega em passos de 100 pA na faixa de 100 µA.
        return round(leitura / DMM_RESOLUCAO) * DMM_RESOLUCAO


# Instância única: os dois drivers de um mesmo experimento têm de ver o mesmo
# filamento. `MockPWS4323_Driver` reinicia o estado ao abrir a "conexão".
_BANCADA = BancadaSimulada()


def bancada_simulada() -> BancadaSimulada:
    return _BANCADA


def reconfigurar_bancada(**kwargs) -> BancadaSimulada:
    """Troca o filamento/LED virtuais (usado pelos testes)."""
    global _BANCADA
    _BANCADA = BancadaSimulada(**kwargs)
    return _BANCADA


# --- DRIVERS FALSOS ----------------------------------------------------------

class MockPWS4323_Driver:
    """Espelha PWS4323_Driver, sem tocar em VISA."""

    def __init__(self, resource_manager=None, resource_string: str = STRING_RECURSO_PWS):
        self.resource_string = resource_string
        self.bancada = bancada_simulada()
        self.bancada.saida_ligada = False
        self.bancada.aplicar_tensao(0.0)
        self.fechado = False

    def configure_safety_limits(self, max_current: float = 1.0):
        self.bancada.limite_corrente = max_current

    def set_output(self, state: bool):
        self.bancada.saida_ligada = bool(state)

    def set_voltage(self, volts: float):
        self.bancada.aplicar_tensao(volts)

    def measure_current(self) -> float:
        return self.bancada.ler_corrente_filamento()

    def measure_voltage(self) -> float:
        """
        Readback de tensão — existe no instrumento real (MEAS:VOLT?) mas ainda
        não é usado pelo software; entra na correção A4 (Fase 2).
        """
        return self.bancada.ler_tensao_filamento()

    def turn_off_safely(self):
        self.bancada.aplicar_tensao(0.0)
        self.bancada.saida_ligada = False

    def close(self):
        self.turn_off_safely()
        self.fechado = True


class MockDMM4050_Driver:
    """Espelha DMM4050_Driver, sem tocar em VISA."""

    def __init__(self, resource_manager=None, resource_string: str = STRING_RECURSO_DMM):
        self.resource_string = resource_string
        self.bancada = bancada_simulada()
        self.nplc = None
        self.faixa = None
        self.fechado = False

    def configure_dc_current(self, nplc: float = 10.0):
        self.nplc = nplc
        self.faixa = 1e-4   # a mesma faixa fixa de 100 µA do driver real

    def read_current(self) -> float:
        return self.bancada.ler_fotocorrente()

    def close(self):
        self.fechado = True
