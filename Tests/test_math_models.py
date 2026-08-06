"""
Testes do modelo físico (Fase 2 — correções A2 e A5).

Roda sem hardware e sem pytest:

    cd Software && python ../Tests/test_math_models.py
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "Software"))

from utils.math_models import (calculate_temperature, calculate_planck_constant,
                               corrigir_r0_para_zero_celsius,
                               selecionar_pontos_validos,
                               simulate_experiment_data, calibrar_dissipacao,
                               resolver_temperatura_regime,
                               resistencia_do_filamento,
                               C, K_B, H_REF, TEMPERATURA_MINIMA_PADRAO,
                               TEMPERATURA_AMBIENTE_K,
                               ANCORA_TENSAO, ANCORA_TEMPERATURA)

ALPHA, BETA = 5.23e-3, 7.0e-7
FALHAS = []


def checa(condicao, descricao, detalhe=""):
    print(f"  [{'ok  ' if condicao else 'FALHA'}] {descricao}{'  -> ' + detalhe if detalhe else ''}")
    if not condicao:
        FALHAS.append(descricao)


print("1. A2 — correção de R0 para 0 °C (Eq. 11 do artigo)")

r_frio, t_amb = 1.2, 25.0
r0 = corrigir_r0_para_zero_celsius(r_frio, t_amb, ALPHA, BETA)
checa(r0 < r_frio, "R0 a 0 °C é menor que a medida a quente ambiente",
      f"{r_frio} Ω a {t_amb} °C -> R0 = {r0:.4f} Ω")

deslocamento = (r_frio - r0) / r0 * 100
checa(12.0 < deslocamento < 14.0,
      "a 25 °C o viés evitado é da ordem de 13%", f"{deslocamento:.1f}%")

# Consistência: aplicar o modelo em T_amb sobre o R0 corrigido tem de devolver
# exatamente a resistência medida.
volta = r0 * (1 + ALPHA * t_amb + BETA * t_amb**2)
checa(abs(volta - r_frio) < 1e-12, "a correção é exatamente inversível",
      f"{volta:.10f} vs {r_frio}")

checa(abs(corrigir_r0_para_zero_celsius(1.2, 0.0, ALPHA, BETA) - 1.2) < 1e-12,
      "medir a 0 °C não altera nada (caso degenerado)")

try:
    corrigir_r0_para_zero_celsius(1.2, -400.0, ALPHA, BETA)
    checa(False, "coeficientes/temperatura absurdos levantam erro")
except ValueError:
    checa(True, "coeficientes/temperatura absurdos levantam erro",
          "divisor não positivo é rejeitado")

# Efeito prático: a mesma resistência medida dá temperaturas diferentes.
r_medido = np.array([10.0])
t_sem = calculate_temperature(r_medido, r_frio, ALPHA, BETA)[0]
t_com = calculate_temperature(r_medido, r0, ALPHA, BETA)[0]
checa(t_com > t_sem, "corrigir R0 desloca a temperatura calculada",
      f"sem correção {t_sem:.0f} K, com correção {t_com:.0f} K "
      f"({(t_com-t_sem)/t_sem*100:+.1f}%)")

print("\n2. Guardas de calculate_temperature (A5)")

# O discriminante só fica negativo para R muito abaixo de R0. Com R0=1,2 e
# estes coeficientes, o limite é R < ~-10,5 Ohm.
t = calculate_temperature(np.array([-20.0]), 1.2, ALPHA, BETA)
checa(np.isnan(t[0]), "resistência sem solução real devolve NaN, não lixo",
      f"{t[0]}")

t = calculate_temperature(np.array([10.0, -20.0, 5.0]), 1.2, ALPHA, BETA)
checa(np.isfinite(t[0]) and np.isnan(t[1]) and np.isfinite(t[2]),
      "o NaN é por ponto, não contamina o vetor inteiro",
      f"{np.round(t, 1)}")

# O caso que de fato aparece na bancada: raiz real, mas absurda. R abaixo de R0
# produz temperaturas abaixo do ambiente (os T ~ 77 K dos CSVs reais); R
# negativa produz Kelvin negativo. Nos dois casos a conta "funciona".
t_absurdo = calculate_temperature(np.array([0.0]), 1.2, ALPHA, BETA)[0]
checa(np.isfinite(t_absurdo) and t_absurdo < 100,
      "R = 0 dá uma raiz real porém absurda (é o T~77 K dos CSVs reais)",
      f"{t_absurdo:.1f} K")

t_negativo = calculate_temperature(np.array([-5.0]), 1.2, ALPHA, BETA)[0]
checa(t_negativo < 0, "R negativa chega a produzir Kelvin negativo",
      f"{t_negativo:.1f} K")

# É a seleção que barra esses pontos, não a inversão do modelo.
mascara = selecionar_pontos_validos(
    np.array([t_absurdo, t_negativo, 2400.0]), np.array([1e-7, 1e-7, 1e-7]),
    t_minima=0.0)
checa(list(mascara) == [True, False, True],
      "mesmo sem corte de temperatura, Kelvin não positivo é sempre barrado",
      f"{list(mascara)}")

mascara = selecionar_pontos_validos(
    np.array([t_absurdo, 2400.0]), np.array([1e-7, 1e-7]),
    t_minima=TEMPERATURA_MINIMA_PADRAO)
checa(list(mascara) == [False, True],
      "e o corte da região de Wien barra também o T~77 K")

# Beta = 0 degenera a quadrática numa reta; não pode dividir por zero.
t_linear = calculate_temperature(np.array([2.4]), 1.2, ALPHA, 0.0)
esperado = (2.4 / 1.2 - 1) / ALPHA + 273.15
checa(abs(t_linear[0] - esperado) < 1e-6,
      "com β = 0 resolve a reta em vez de dividir por zero",
      f"{t_linear[0]:.2f} K")

checa(np.isnan(calculate_temperature(np.array([2.4]), 1.2, 0.0, 0.0)[0]),
      "sem α nem β não há como inverter: NaN")

print("\n3. A5 — seleção da região de Wien")

T = np.array([300.0, 1000.0, 1700.0, 1900.0, 2300.0, np.nan, 0.0])
I = np.array([5e-9, 6e-9, 8e-9, 5e-8, 3e-7, 1e-7, 1e-7])

sem_corte = selecionar_pontos_validos(T, I, t_minima=0.0)
checa(not sem_corte[5] and not sem_corte[6],
      "NaN e T=0 são sempre descartados, mesmo sem corte de temperatura")

com_corte = selecionar_pontos_validos(T, I, t_minima=1800.0)
checa(list(com_corte) == [False, False, False, True, True, False, False],
      "o corte mantém só a região quente", f"{list(com_corte)}")

checa(np.sum(selecionar_pontos_validos(T, I, 1800.0)) <=
      np.sum(selecionar_pontos_validos(T, I, 0.0)),
      "aumentar t_minima nunca aumenta o número de pontos")

# Depois do B6, o limiar padrão de corrente já elimina sozinho os pontos de
# piso — mesmo sem corte de temperatura. Os dois filtros se reforçam.
checa(np.sum(selecionar_pontos_validos(T, I, 0.0, limiar_corrente=1e-9)) >
      np.sum(selecionar_pontos_validos(T, I, 0.0)),
      "o limiar derivado (25 nA) descarta mais que o antigo de 1 nA",
      f"{int(np.sum(selecionar_pontos_validos(T, I, 0.0, limiar_corrente=1e-9)))} pontos com 1 nA "
      f"vs {int(np.sum(selecionar_pontos_validos(T, I, 0.0)))} com o limiar do datasheet")

so_piso = selecionar_pontos_validos(np.array([2500.0]), np.array([5e-10]), 0.0)
checa(not so_piso[0], "fotocorrente abaixo do limiar é descartada mesmo quente")

print("\n4. A regressão recupera h de dados perfeitos")

# Dados sintéticos exatos: ln(I) = const - (hc/(lambda*k_B))/T, sem ruído.
lam_nm = 590.0
T_ideal = np.linspace(1800, 3000, 40)
m_ideal = -(H_REF * C) / (lam_nm * 1e-9 * K_B)
I_ideal = np.exp(m_ideal / T_ideal + 5.0)

h, erro, m, c, r2 = calculate_planck_constant(T_ideal, I_ideal, lam_nm)
checa(erro < 1e-6, "sem ruído, h é recuperado exatamente",
      f"h={h:.6e}, erro {erro:.2e}%")
checa(abs(r2 - 1.0) < 1e-9, "e o ajuste é perfeito", f"R²={r2:.10f}")
checa(abs(m - m_ideal) / abs(m_ideal) < 1e-9, "a inclinação bate com a teórica")

# Com pontos de piso somados abaixo de 1800 K, o corte tem de salvar o ajuste.
T_frio = np.linspace(400, 1700, 20)
I_frio = np.full_like(T_frio, 4.5e-9)
T_tudo = np.concatenate([T_frio, T_ideal])
I_tudo = np.concatenate([I_frio, I_ideal])

# Com o limiar ANTIGO de 1 nA (menor que o piso de 4,5 nA), os pontos de piso
# entravam e envenenavam o ajuste.
_, erro_antigo, _, _, r2_antigo = calculate_planck_constant(
    T_tudo, I_tudo, lam_nm, t_minima=0.0, limiar_corrente=1e-9)
checa(erro_antigo > 10.0,
      "com o limiar antigo de 1 nA, os pontos de piso estragam o ajuste",
      f"erro {erro_antigo:.1f}%, R²={r2_antigo:.4f}")

# Com o limiar derivado do datasheet (B6), eles caem fora sozinhos — sem
# precisar sequer do corte de temperatura.
_, erro_b6, _, _, r2_b6 = calculate_planck_constant(T_tudo, I_tudo, lam_nm, t_minima=0.0)
checa(erro_b6 < 1e-6,
      "o limiar derivado (B6) sozinho já devolve o resultado exato",
      f"erro {erro_b6:.2e}%, R²={r2_b6:.6f}")

# E os dois filtros juntos continuam corretos.
_, erro_com, _, _, r2_com = calculate_planck_constant(
    T_tudo, I_tudo, lam_nm, t_minima=TEMPERATURA_MINIMA_PADRAO)
checa(erro_com < 1e-6, "com corte de temperatura também",
      f"erro {erro_com:.2e}%, R²={r2_com:.6f}")

print("\n5. A9 — a simulação resolve T(V) pelo balanço de energia")

R0_SIM = 1.2
volts = np.arange(0.0, 12.5, 0.5)
V, i_fil, R_fil, T_sim, I_led = simulate_experiment_data(
    volts, R0_SIM, ALPHA, BETA, 590.0, noise_level=0.0, semente=42)

# O defeito original: T era linspace(1500, 3000) fosse qual fosse a tensão.
checa(abs(T_sim[0] - TEMPERATURA_AMBIENTE_K) < 1.0,
      "em 0 V o filamento está na temperatura ambiente, não a 1500 K",
      f"{T_sim[0]:.1f} K")
checa(np.all(np.diff(T_sim) > 0), "T cresce monotonicamente com V")

indice_12v = int(np.argmin(np.abs(V - ANCORA_TENSAO)))
checa(abs(T_sim[indice_12v] - ANCORA_TEMPERATURA) < 5.0,
      "a 12 V bate a âncora medida na bancada real",
      f"{T_sim[indice_12v]:.0f} K (âncora {ANCORA_TEMPERATURA:.0f} K)")

# Metade da tensão NÃO é metade da temperatura — a relação é a do balanço
# de energia, dominado por T⁴ no topo da varredura.
indice_6v = int(np.argmin(np.abs(V - 6.0)))
checa(T_sim[indice_6v] > 0.7 * T_sim[indice_12v],
      "a relação V→T é a do balanço de energia (T⁴), não uma reta",
      f"T(6 V) = {T_sim[indice_6v]:.0f} K vs T(12 V) = {T_sim[indice_12v]:.0f} K")

# Consistência interna que o linspace violava: os três vetores derivam um do
# outro. Inverter R pelo próprio modelo tem de devolver o T simulado.
T_volta = calculate_temperature(R_fil[1:], R0_SIM, ALPHA, BETA)
checa(np.allclose(T_volta, T_sim[1:], rtol=1e-6),
      "V → T → R é inversível: calculate_temperature(R) devolve o T simulado")
checa(np.allclose(i_fil[1:], V[1:] / R_fil[1:]),
      "corrente do filamento é V/R, coerente com os demais vetores")

# O balanço de energia fecha em todos os pontos quentes.
k_rad, k_cond = calibrar_dissipacao(R0_SIM, ALPHA, BETA)
entregue = V[1:]**2 / R_fil[1:]
dissipada = (k_rad * (T_sim[1:]**4 - TEMPERATURA_AMBIENTE_K**4)
             + k_cond * (T_sim[1:] - TEMPERATURA_AMBIENTE_K))
checa(np.allclose(entregue, dissipada, rtol=1e-4),
      "potência entregue = potência dissipada em todos os pontos",
      f"resíduo máximo {np.max(np.abs(entregue/dissipada - 1))*100:.4f}%")

# A física é a MESMA do mock: o mesmo solver, os mesmos números.
t_solver = resolver_temperatura_regime(9.0, R0_SIM, ALPHA, BETA, k_rad, k_cond)
indice_9v = int(np.argmin(np.abs(V - 9.0)))
checa(abs(t_solver - T_sim[indice_9v]) < 1e-6,
      "simulação e bancada simulada compartilham o mesmo solver",
      f"{t_solver:.2f} K")

print("\n5b. A9 — o h da CODATA está embutido e é recuperável")

# Sem ruído e sem fuga: a cadeia inteira tem de devolver h exatamente.
_, _, _, T_puro, I_puro = simulate_experiment_data(
    volts, R0_SIM, ALPHA, BETA, 590.0, noise_level=0.0, fuga_dmm=0.0)
h_puro, erro_puro, _, _, r2_puro = calculate_planck_constant(
    T_puro, I_puro, 590.0, t_minima=TEMPERATURA_MINIMA_PADRAO)
checa(erro_puro < 1e-6, "sem ruído nem fuga, h volta exato",
      f"erro {erro_puro:.2e}%, R²={r2_puro:.8f}")

# Com os artefatos padrão (ruído 5% + fuga de 4,5 nA), ainda se recupera h
# com a qualidade dos experimentos reais. O limite de 8% vem de medir a
# distribuição em 40 sementes: mediana 4,2%, máximo 6,8% — o grosso é o viés
# sistemático da fuga nos pontos mais frios que sobrevivem à seleção, o mesmo
# efeito observado na bancada.
_, _, _, T_real, I_real = simulate_experiment_data(
    volts, R0_SIM, ALPHA, BETA, 590.0, semente=7)
h_real, erro_real, _, _, r2_real = calculate_planck_constant(
    T_real, I_real, 590.0, t_minima=TEMPERATURA_MINIMA_PADRAO)
checa(erro_real < 8.0, "com ruído e fuga realistas, erro na casa dos %",
      f"erro {erro_real:.2f}%, R²={r2_real:.4f}")

# A fuga reproduz o fenômeno dos CSVs reais: pontos frios lendo ~4,5 nA.
frios = T_real < 1000
checa(bool(np.any(frios)) and float(np.median(I_real[frios])) > 3e-9,
      "pontos frios leem o fundo do DMM, como na bancada real",
      f"mediana fria {np.median(I_real[frios]):.2e} A")

checa(np.allclose(
        simulate_experiment_data(volts, R0_SIM, ALPHA, BETA, 590.0, semente=3)[4],
        simulate_experiment_data(volts, R0_SIM, ALPHA, BETA, 590.0, semente=3)[4]),
      "a mesma semente reproduz a mesma varredura (testes determinísticos)")

if FALHAS:
    print(f"\n{len(FALHAS)} FALHA(S): " + "; ".join(FALHAS))
    sys.exit(1)
print("\nTodos os testes do modelo físico passaram.")
