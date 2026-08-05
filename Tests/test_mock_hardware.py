"""
Testes da bancada simulada (Fase 1).

Roda sem hardware e sem pytest:

    cd Software && python ../Tests/test_mock_hardware.py

Verifica três coisas: que os mocks são substituíveis pelos drivers reais, que
a física simulada está calibrada com os dados da bancada, e que o software
consegue recuperar h dos dados que o mock gera.
"""
import inspect
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "Software"))

from core.hardware_manager import (PWS4323_Driver, DMM4050_Driver, obter_drivers)
from core.mock_hardware import (MockPWS4323_Driver, MockDMM4050_Driver,
                                BancadaSimulada, reconfigurar_bancada,
                                ANCORA_TEMPERATURA, ANCORA_FOTOCORRENTE,
                                T_AMBIENTE, DMM_FUGA)
from utils.math_models import calculate_temperature, calculate_planck_constant, H_REF

FALHAS = []


def checa(condicao, descricao, detalhe=""):
    print(f"  [{'ok  ' if condicao else 'FALHA'}] {descricao}{'  -> ' + detalhe if detalhe else ''}")
    if not condicao:
        FALHAS.append(descricao)


def metodos_publicos(classe):
    return {n for n, _ in inspect.getmembers(classe, inspect.isfunction)
            if not n.startswith("_")}


print("1. Os mocks são substituíveis pelos drivers reais")
faltando_pws = metodos_publicos(PWS4323_Driver) - metodos_publicos(MockPWS4323_Driver)
faltando_dmm = metodos_publicos(DMM4050_Driver) - metodos_publicos(MockDMM4050_Driver)
checa(not faltando_pws, "MockPWS4323_Driver cobre a interface da fonte", str(faltando_pws))
checa(not faltando_dmm, "MockDMM4050_Driver cobre a interface do multímetro", str(faltando_dmm))
checa(obter_drivers(True) == (MockPWS4323_Driver, MockDMM4050_Driver),
      "obter_drivers(True) devolve os simulados")
checa(obter_drivers(False) == (PWS4323_Driver, DMM4050_Driver),
      "obter_drivers(False) devolve os reais")

print("\n2. Calibração da física simulada")
b = BancadaSimulada(semente=1)
b.saida_ligada = True
b.aplicar_tensao(12.0)
_, _, t12 = b.estado_eletrico()
checa(abs(t12 - ANCORA_TEMPERATURA) < 5,
      f"12 V leva o filamento à âncora de {ANCORA_TEMPERATURA:.0f} K", f"{t12:.1f} K")

leituras = [b.ler_fotocorrente() for _ in range(50)]
media = float(np.mean(leituras))
checa(abs(media - ANCORA_FOTOCORRENTE) / ANCORA_FOTOCORRENTE < 0.05,
      f"fotocorrente na âncora ≈ {ANCORA_FOTOCORRENTE:.2e} A", f"{media:.3e} A")

temperaturas = []
for v in [1.0, 3.0, 5.0, 7.0, 9.0, 11.0]:
    b.aplicar_tensao(v)
    temperaturas.append(b.estado_eletrico()[2])
checa(all(x < y for x, y in zip(temperaturas, temperaturas[1:])),
      "T cresce monotonicamente com a tensão",
      " < ".join(f"{t:.0f}" for t in temperaturas))

print("\n3. Comportamentos do instrumento que o mock precisa reproduzir")
b.aplicar_tensao(1.0)
_, _, t_frio = b.estado_eletrico()
piso = float(np.mean([b.ler_fotocorrente() for _ in range(50)]))
checa(abs(piso - DMM_FUGA) < 2e-9,
      "em T baixa a leitura é o piso do DMM, não sinal",
      f"T={t_frio:.0f} K, lê {piso:.2e} A (piso {DMM_FUGA:.1e})")

b.saida_ligada = False
_, corrente_desligada, t_desligado = b.estado_eletrico()
checa(corrente_desligada == 0.0 and t_desligado == T_AMBIENTE,
      "saída desligada zera a corrente e volta ao ambiente")

b2 = BancadaSimulada(semente=2)
b2.saida_ligada = True
b2.limite_corrente = 0.30
b2.aplicar_tensao(12.0)
tensao_cc, corrente_cc, _ = b2.estado_eletrico()
checa(abs(corrente_cc - 0.30) < 1e-9 and tensao_cc < 12.0,
      "limite de corrente joga a fonte em modo CC",
      f"i={corrente_cc:.3f} A, V cai para {tensao_cc:.2f} V")

pws = MockPWS4323_Driver()
pws.set_output(True)
pws.set_voltage(10.0)
checa(abs(pws.measure_voltage() - 10.0) < 0.05,
      "readback de tensão fica perto do programado", f"{pws.measure_voltage():.4f} V")
pws.turn_off_safely()
checa(pws.measure_current() < 1e-2, "turn_off_safely corta a corrente")

print("\n4. O software recupera h dos dados que o mock gera")


def varredura(v_start, v_end, v_step, semente=7):
    reconfigurar_bancada(r0=1.2, semente=semente)
    fonte, multimetro = MockPWS4323_Driver(), MockDMM4050_Driver()
    fonte.configure_safety_limits(2.0)
    multimetro.configure_dc_current(10.0)
    fonte.set_output(True)
    temperaturas, fotocorrentes = [], []
    for v in np.arange(v_start, v_end + v_step, v_step):
        fonte.set_voltage(v)
        i = max(fonte.measure_current(), 1e-6)
        temperaturas.append(
            calculate_temperature(np.array([v / i]), 1.2, 5.23e-3, 7.0e-7)[0]
        )
        fotocorrentes.append(multimetro.read_current())
    fonte.close()
    multimetro.close()
    return np.array(temperaturas), np.array(fotocorrentes)


T, L = varredura(6.0, 12.0, 0.2)
h, erro, _, _, r2 = calculate_planck_constant(T, L, 590.0)
checa(erro < 5.0, "na região de Wien (6–12 V) h sai a menos de 5% do valor real",
      f"h={h:.4e} J·s, erro {erro:.2f}%, R²={r2:.4f}")
checa(r2 > 0.99, "a regressão na região de Wien é linear", f"R²={r2:.4f}")

# Este NÃO é um defeito do mock: é o defeito A5/B6 do software, reproduzido de
# propósito. Os pontos frios são piso de 4,5 nA, passam no limiar de 1 nA da
# regressão e a envenenam. As Fases 2 e 3 é que corrigem isso — e este teste
# vira a prova de que corrigiram.
T, L = varredura(0.5, 12.0, 0.5)
h_todos, erro_todos, _, _, r2_todos = calculate_planck_constant(T, L, 590.0)
checa(erro_todos > 20.0,
      "varredura completa ainda erra feio (A5/B6 por corrigir na Fase 2/3)",
      f"h={h_todos:.4e}, erro {erro_todos:.1f}%, R²={r2_todos:.4f}")

T1, L1 = varredura(6.0, 12.0, 0.5, semente=42)
T2, L2 = varredura(6.0, 12.0, 0.5, semente=42)
checa(np.array_equal(T1, T2) and np.array_equal(L1, L2),
      "a mesma semente reproduz a mesma varredura")

print(f"\nh de referência: {H_REF:.4e} J·s")
if FALHAS:
    print(f"\n{len(FALHAS)} FALHA(S): " + "; ".join(FALHAS))
    sys.exit(1)
print("\nTodos os testes da bancada simulada passaram.")
