"""
Testes da teoria de erros (Fase 3).

Roda sem hardware e sem pytest:

    cd Software && python ../Tests/test_error_models.py

O objetivo aqui não é só "não quebrar": é CONFERIR A MATEMÁTICA contra casos
com resposta conhecida, para que a fundamentação possa ser defendida.
"""
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "Software"))

from utils import error_models as em
from utils.math_models import (H_REF, C, K_B, LIMIAR_CORRENTE_PADRAO,
                               corrigir_r0_para_zero_celsius)

FALHAS = []


def checa(condicao, descricao, detalhe=""):
    print(f"  [{'ok  ' if condicao else 'FALHA'}] {descricao}{'  -> ' + detalhe if detalhe else ''}")
    if not condicao:
        FALHAS.append(descricao)


def perto(a, b, tol=1e-9):
    return abs(a - b) <= tol * max(1.0, abs(a), abs(b))


print("1. Incerteza Tipo B a partir do datasheet (E2, E6)")

spec = em.DMM4050_CORRENTE_100UA
# Uma leitura de 1 uA: limite = 0,05% de 1e-6 + 25 nA = 0,5 nA + 25 nA
checa(perto(spec.limite(1e-6), 0.0005 * 1e-6 + 25e-9),
      "limite = pct da leitura + termo fixo", f"{spec.limite(1e-6):.4e} A")
checa(perto(spec.incerteza_padrao(1e-6), spec.limite(1e-6) / math.sqrt(3)),
      "incerteza padrão = limite / raiz(3) (retangular)",
      f"{float(spec.incerteza_padrao(1e-6)):.4e} A")
checa(perto(float(spec.incerteza_padrao(0.0)), 25e-9 / math.sqrt(3)),
      "com leitura zero sobra só o termo de fundo",
      f"{float(spec.incerteza_padrao(0.0)):.4e} A")

# Domínio do termo fixo: em correntes pequenas ele é tudo.
fracao_fundo = spec.termo_fixo / spec.limite(50e-9)
checa(fracao_fundo > 0.99,
      "a 50 nA o termo de fundo responde por praticamente toda a incerteza",
      f"{fracao_fundo*100:.1f}%")

print("\n2. Incerteza Tipo A por repetição (E1)")

media, u_a = em.incerteza_tipo_a([10.0])
checa(media == 10.0 and u_a == 0.0, "uma leitura só: sem informação estatística")

amostra = [10.0, 10.2, 9.8, 10.1, 9.9]
media, u_a = em.incerteza_tipo_a(amostra)
esperado = np.std(amostra, ddof=1) / math.sqrt(len(amostra))
checa(perto(media, 10.0) and perto(u_a, esperado),
      "u_A = s/raiz(N) com desvio amostral (ddof=1)", f"u_A={u_a:.5f}")

_, u_a_grande = em.incerteza_tipo_a(list(np.array(amostra) * 1))
checa(u_a < np.std(amostra, ddof=1),
      "a média é mais precisa que uma leitura individual")

checa(perto(em.combinar(3.0, 4.0), 5.0), "combinação em quadratura (E3)", "3 (+) 4 = 5")

print("\n3. B6 — o limiar sai do instrumento (E7)")

limiar = em.limiar_corrente_confiavel()
checa(24e-9 < limiar < 26e-9,
      "o limiar derivado fica na casa do termo de fundo do DMM",
      f"{limiar*1e9:.3f} nA")
checa(perto(limiar, LIMIAR_CORRENTE_PADRAO, tol=1e-3),
      "a constante replicada em math_models concorda com a derivação",
      f"{LIMIAR_CORRENTE_PADRAO*1e9:.1f} nA vs {limiar*1e9:.3f} nA")
checa(limiar > 1e-9 * 20,
      "e é muito maior que o antigo limiar de 1 nA, que não filtrava nada",
      f"{limiar/1e-9:.1f}x maior")
checa(em.limiar_corrente_confiavel(razao_sinal_ruido=10) > limiar,
      "exigir mais sinal/ruído sobe o limiar")

print("\n4. Derivadas da temperatura: analítico vs numérico (E9–E12)")

from utils.math_models import calculate_temperature

R0, ALPHA, BETA = 1.0608, 5.23e-3, 7.0e-7
r_teste = 10.0
t_teste = float(calculate_temperature(np.array([r_teste]), R0, ALPHA, BETA)[0])
d = em.derivadas_temperatura(t_teste, R0, ALPHA, BETA)


def derivada_numerica(funcao, valor, passo_rel=1e-6):
    passo = abs(valor) * passo_rel
    return (funcao(valor + passo) - funcao(valor - passo)) / (2 * passo)


num_r = derivada_numerica(
    lambda r: float(calculate_temperature(np.array([r]), R0, ALPHA, BETA)[0]), r_teste)
checa(perto(float(d["R"]), num_r, tol=1e-5),
      "dT/dR confere com a derivada numérica",
      f"analítico {float(d['R']):.4f} vs numérico {num_r:.4f} K/ohm")

num_r0 = derivada_numerica(
    lambda r0: float(calculate_temperature(np.array([r_teste]), r0, ALPHA, BETA)[0]), R0)
checa(perto(float(d["R0"]), num_r0, tol=1e-5),
      "dT/dR0 confere", f"analítico {float(d['R0']):.2f} vs numérico {num_r0:.2f}")

num_a = derivada_numerica(
    lambda a: float(calculate_temperature(np.array([r_teste]), R0, a, BETA)[0]), ALPHA)
checa(perto(float(d["alpha"]), num_a, tol=1e-4),
      "dT/dalpha confere", f"analítico {float(d['alpha']):.1f} vs numérico {num_a:.1f}")

num_b = derivada_numerica(
    lambda b: float(calculate_temperature(np.array([r_teste]), R0, ALPHA, b)[0]), BETA)
checa(perto(float(d["beta"]), num_b, tol=1e-4),
      "dT/dbeta confere", f"analítico {float(d['beta']):.3e} vs numérico {num_b:.3e}")

checa(float(d["R"]) > 0 and float(d["R0"]) < 0,
      "sinais coerentes: R maior aquece, R0 maior esfria a estimativa")

print("\n5. Propagação da resistência (E8)")

u_r = em.incerteza_resistencia(10.0, 0.5, 0.01, 0.001)
esperado = (10.0 / 0.5) * math.sqrt((0.01 / 10.0) ** 2 + (0.001 / 0.5) ** 2)
checa(perto(float(u_r), esperado), "incertezas relativas somam em quadratura",
      f"{float(u_r):.5f} ohm")

u_r_cabos = em.incerteza_resistencia(10.0, 0.5, 0.01, 0.001, u_r_cabos=0.05)
checa(float(u_r_cabos) > float(u_r), "incerteza dos cabos aumenta a de R")

print("\n6. Ajuste ponderado (E15–E20)")

# Caso 1: pesos iguais têm de reproduzir o ajuste comum.
rng = np.random.default_rng(3)
x = np.linspace(1.0, 5.0, 30)
y_verdadeiro = 2.5 * x - 1.3
y = y_verdadeiro + rng.normal(0, 0.05, x.size)
u_y = np.full_like(x, 0.05)

ajuste = em.ajuste_linear_ponderado(x, y, u_y)
m_np, c_np = np.polyfit(x, y, 1)
checa(perto(ajuste.m, m_np, tol=1e-9) and perto(ajuste.c, c_np, tol=1e-9),
      "com pesos uniformes, bate com numpy.polyfit",
      f"m={ajuste.m:.8f} vs {m_np:.8f}")

# Caso 2: incerteza do coeficiente contra a fórmula fechada conhecida.
# Para pesos uniformes w = 1/s^2:  u_m = s / sqrt(Sxx - (Sx)^2/N)
s = 0.05
sxx = np.sum(x ** 2)
sx = np.sum(x)
u_m_fechado = s / math.sqrt(sxx - sx ** 2 / x.size)
checa(perto(ajuste.u_m, u_m_fechado, tol=1e-9),
      "u_m bate com a fórmula analítica para pesos uniformes",
      f"{ajuste.u_m:.8f} vs {u_m_fechado:.8f}")

# Caso 3: ponderação faz diferença quando um ponto é péssimo.
y_ruim = y.copy(); y_ruim[-1] += 5.0
u_y_ruim = u_y.copy(); u_y_ruim[-1] = 5.0        # e o sabemos péssimo
m_ponderado = em.ajuste_linear_ponderado(x, y_ruim, u_y_ruim).m
m_ignorando = np.polyfit(x, y_ruim, 1)[0]
checa(abs(m_ponderado - 2.5) < abs(m_ignorando - 2.5),
      "ponderar protege o ajuste de um ponto ruim declarado como tal",
      f"ponderado {m_ponderado:.4f} vs não ponderado {m_ignorando:.4f} (real 2,5)")

# Caso 4: chi2 reduzido diagnostica a coerência das incertezas.
checa(0.3 < ajuste.chi2_reduzido < 3.0,
      "chi2 reduzido perto de 1 quando as incertezas são realistas",
      f"{ajuste.chi2_reduzido:.3f}")

exagerado = em.ajuste_linear_ponderado(x, y, u_y * 10)
checa(exagerado.chi2_reduzido < 0.1,
      "incertezas superestimadas derrubam o chi2 reduzido",
      f"{exagerado.chi2_reduzido:.4f}")

# Caso 5: erro em x muda o resultado e converge.
u_x = np.full_like(x, 0.05)
com_x = em.ajuste_linear_ponderado(x, y, u_y, u_x)
checa(com_x.iteracoes > 0, "com erro em x, o método itera",
      f"{com_x.iteracoes} iterações")
checa(com_x.u_m > ajuste.u_m,
      "reconhecer erro em x aumenta a incerteza da inclinação",
      f"{com_x.u_m:.6f} vs {ajuste.u_m:.6f}")

print("\n7. De volta a h (E21, E22)")

m_teorico = -(H_REF * C) / (590e-9 * K_B)
u_h, orcamento = em.incerteza_h(m_teorico, abs(m_teorico) * 0.01, 590.0,
                                em.incerteza_lambda(30.0))
h_calc = -(m_teorico * 590e-9 * K_B) / C
checa(perto(h_calc, H_REF, tol=1e-12), "a inclinação teórica devolve h de referência",
      f"{h_calc:.6e}")

rel_lambda = em.incerteza_lambda(30.0) / 590.0
rel_total = math.sqrt(0.01 ** 2 + rel_lambda ** 2)
checa(perto(u_h, abs(h_calc) * rel_total, tol=1e-9),
      "u_h combina as relativas da inclinação e de lambda",
      f"u_h/h = {u_h/abs(h_calc)*100:.2f}%")
checa(orcamento["lambda"] > orcamento["inclinacao"],
      "com 1% de erro na inclinação, lambda domina o orçamento",
      f"lambda {orcamento['lambda']/(sum(orcamento.values()))*100:.0f}% do total")

checa(perto(em.incerteza_lambda(30.0), 30.0 / math.sqrt(3)),
      "u_lambda = delta_lambda / raiz(3)", f"{em.incerteza_lambda(30.0):.3f} nm")

print("\n8. Formatação metrológica")

texto = em.formatar_com_incerteza(6.626e-34, 2.1e-35, "J·s")
checa("±" in texto and "10^-34" in texto, "sai no formato (valor ± U)×10^n", texto)
checa(texto.count(".") <= 3 and "6.63" in texto.replace(",", "."),
      "o valor é arredondado na casa da incerteza, sem dígitos falsos", texto)

print("\n9. A cadeia completa, ponta a ponta")

# Dados sintéticos coerentes: filamento com R(T) conhecido e Wien exato.
r0_v, alpha_v, beta_v, lam = 1.2, 5.23e-3, 7.0e-7, 590.0
temperaturas = np.linspace(1900, 2900, 30)
tc = temperaturas - 273.15
resistencias = r0_v * (1 + alpha_v * tc + beta_v * tc ** 2)
correntes = np.linspace(0.45, 0.62, 30)
tensoes = resistencias * correntes
fotocorrentes = 1.0e-2 * np.exp(-(H_REF * C) / (lam * 1e-9 * K_B * temperaturas))

resultado = em.analisar_experimento(
    tensoes, correntes, fotocorrentes,
    r0=r0_v, alpha=alpha_v, beta=beta_v, lambda_nm=lam,
    delta_lambda_nm=30.0, t_minima=1800.0)

checa(resultado.erro_relativo < 1.0,
      "sem ruído, a cadeia recupera h com erro abaixo de 1%",
      f"h={resultado.h:.4e}, erro {resultado.erro_relativo:.3f}%")
checa(resultado.compativel_com_codata,
      "e o valor da CODATA cai dentro da incerteza expandida",
      f"U = {resultado.incerteza_expandida:.2e}")
checa(resultado.n_usados == resultado.n_total,
      "todos os pontos quentes foram usados",
      f"{resultado.n_usados}/{resultado.n_total}")

principais = resultado.orcamento_ordenado()
checa(principais and principais[0][0] == "lambda",
      "lambda é a maior fonte de incerteza em h",
      "; ".join(f"{nome} {pct:.1f}%" for nome, pct in principais))
checa(abs(sum(pct for _, pct in principais) - 100) < 1e-6,
      "o orçamento fecha em 100%")
checa("±" in resultado.texto, "o resultado se apresenta formatado", resultado.texto)

# Poucos pontos: tem de recusar, não devolver número sem sentido.
try:
    em.analisar_experimento(tensoes[:2], correntes[:2], fotocorrentes[:2],
                            r0=r0_v, alpha=alpha_v, beta=beta_v, lambda_nm=lam)
    checa(False, "com menos de 3 pontos válidos, recusa analisar")
except ValueError:
    checa(True, "com menos de 3 pontos válidos, recusa analisar")

# Incerteza de R0 propaga até h.
com_u_r0 = em.analisar_experimento(
    tensoes, correntes, fotocorrentes,
    r0=r0_v, alpha=alpha_v, beta=beta_v, lambda_nm=lam,
    delta_lambda_nm=30.0, t_minima=1800.0, u_r0=0.05)
checa(com_u_r0.u_h >= resultado.u_h,
      "declarar incerteza em R0 não diminui a incerteza de h",
      f"{com_u_r0.u_h:.3e} vs {resultado.u_h:.3e}")
checa(com_u_r0.orcamento_temperatura["R0"] > 0,
      "e aparece no orçamento da temperatura",
      f"R0 responde por {com_u_r0.orcamento_temperatura['R0']:.1f}% de u_T")

print("\n10. Separação aleatório × sistemático (H3b)")

# Um sistemático NÃO pode entrar no peso dos pontos: ele desloca todas as
# temperaturas juntas, não espalha os pontos. Se entrasse, o chi2 reduzido
# despencaria — o ajuste acharia que os dados são muito melhores do que suas
# incertezas declaradas.
ruido = np.random.default_rng(11).normal(0, 0.01, temperaturas.size)
foto_ruidosa = fotocorrentes * (1 + ruido)

sem_sistematico = em.analisar_experimento(
    tensoes, correntes, foto_ruidosa,
    r0=r0_v, alpha=alpha_v, beta=beta_v, lambda_nm=lam, t_minima=1800.0)
com_sistematico = em.analisar_experimento(
    tensoes, correntes, foto_ruidosa,
    r0=r0_v, alpha=alpha_v, beta=beta_v, lambda_nm=lam, t_minima=1800.0,
    u_r0=0.05)

checa(perto(sem_sistematico.ajuste.chi2_reduzido,
            com_sistematico.ajuste.chi2_reduzido, tol=1e-9),
      "declarar u_R0 NÃO altera o chi2 reduzido (não entrou no peso)",
      f"{sem_sistematico.ajuste.chi2_reduzido:.4f} vs {com_sistematico.ajuste.chi2_reduzido:.4f}")
checa(perto(sem_sistematico.ajuste.u_m, com_sistematico.ajuste.u_m, tol=1e-9),
      "nem a incerteza da inclinação (que é do ajuste, aleatória)")
checa(com_sistematico.u_h > sem_sistematico.u_h,
      "mas AUMENTA a incerteza final de h, como contribuição separada",
      f"{com_sistematico.u_h:.3e} vs {sem_sistematico.u_h:.3e}")
checa("R0" in com_sistematico.orcamento_h,
      "e aparece com nome próprio no orçamento de h",
      "; ".join(f"{n} {p:.1f}%" for n, p in com_sistematico.orcamento_ordenado()))

# ATENÇÃO ao interpretar o chi2 reduzido neste experimento.
#
# Ele fica bem ABAIXO de 1, e isso é esperado, não é defeito. A incerteza da
# fotocorrente vem de uma especificação de datasheet, que é um LIMITE tratado
# como distribuição retangular — e o ruído real do instrumento é bem menor que
# o pior caso que o fabricante garante. Declarar o limite e observar dispersão
# menor que ele produz chi2 reduzido pequeno por construção.
#
# O chi2 só deve tender a 1 quando a incerteza declarada é o desvio padrão
# verdadeiro do processo aleatório — situação verificada na seção 6, onde o
# ruído injetado e a incerteza declarada são o mesmo número.
u_declarada = float(em.DMM4050_CORRENTE_100UA.incerteza_padrao(1e-7)) / 1e-7
razao = 0.01 / u_declarada
checa(sem_sistematico.ajuste.chi2_reduzido < 1.0,
      "chi2 reduzido < 1: o ruído real é menor que o limite do datasheet",
      f"chi2_red={sem_sistematico.ajuste.chi2_reduzido:.3f}; ruído injetado é "
      f"{razao*100:.0f}% da incerteza declarada")
checa(abs(sem_sistematico.ajuste.chi2_reduzido - razao ** 2) < 0.5,
      "e seu valor é aproximadamente (ruído real / incerteza declarada)²",
      f"{sem_sistematico.ajuste.chi2_reduzido:.3f} vs {razao**2:.3f} esperado")

# A sensibilidade tem de crescer com o tamanho do sistemático.
dobro = em.analisar_experimento(
    tensoes, correntes, foto_ruidosa,
    r0=r0_v, alpha=alpha_v, beta=beta_v, lambda_nm=lam, t_minima=1800.0,
    u_r0=0.10)
checa(dobro.orcamento_h["R0"] > com_sistematico.orcamento_h["R0"],
      "dobrar u_R0 aumenta a contribuição sistemática de R0")

print("\n11. Incerteza de R0 corrigido (A2 + propagação)")

u_r0_calc = em.incerteza_r0_corrigido(1.2, 25.0, 5.23e-3, 7.0e-7,
                                      u_r_frio=0.01, u_t_ambiente=2.0)
checa(u_r0_calc > 0, "há incerteza em R0 mesmo com a correção aplicada",
      f"u_R0 = {u_r0_calc:.5f} ohm")

so_resistencia = em.incerteza_r0_corrigido(1.2, 25.0, 5.23e-3, 7.0e-7,
                                           u_r_frio=0.01, u_t_ambiente=0.0)
checa(u_r0_calc > so_resistencia,
      "não saber a temperatura ambiente aumenta a incerteza de R0",
      f"{u_r0_calc:.5f} vs {so_resistencia:.5f} ohm")

if FALHAS:
    print(f"\n{len(FALHAS)} FALHA(S): " + "; ".join(FALHAS))
    sys.exit(1)
print("\nTodos os testes da teoria de erros passaram.")
