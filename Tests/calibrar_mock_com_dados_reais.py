"""
Derivação das constantes térmicas da bancada simulada, a partir dos CSVs reais.

    cd Software && python ../Tests/calibrar_mock_com_dados_reais.py

Não é um teste: é o script que PRODUZIU os números `RAZAO_COND_RAD` e a âncora
de calibração usados em `core/mock_hardware.py`. Fica versionado para que a
procedência daqueles valores seja verificável e refazível — se novas coletas
forem acrescentadas a `data_backup/`, basta rodar de novo.

O modelo ajustado é o balanço de energia em regime estacionário:

    V·i = k_rad·(T⁴ − T_amb⁴) + k_cond·(T − T_amb)

O primeiro termo é radiação (Stefan-Boltzmann); o segundo agrupa condução e
convecção, que dominam em temperatura baixa. Como ambos entram linearmente,
k_rad e k_cond saem de mínimos quadrados lineares comuns.
"""
import csv
import glob
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "Software"))

# Parâmetros da corrida real: R0 deduzido dos próprios CSVs (ver PENDENCIAS P5
# — foi a ausência de metadados que obrigou a essa dedução).
R0_HISTORICO = 0.42
ALPHA, BETA = 5.23e-3, 7.0e-7
T_AMBIENTE = 298.15


def temperatura_de(resistencia):
    """Bhaskara, com os parâmetros da corrida histórica."""
    disc = (R0_HISTORICO * ALPHA) ** 2 - 4 * (R0_HISTORICO * BETA) * (R0_HISTORICO - resistencia)
    if disc < 0:
        return np.nan
    return (-(R0_HISTORICO * ALPHA) + np.sqrt(disc)) / (2 * R0_HISTORICO * BETA) + 273.15


def carregar_pontos():
    tensoes, correntes = [], []
    for arquivo in sorted(glob.glob("data_backup/exp_planck_*.csv")):
        with open(arquivo, newline="", encoding="utf-8") as f:
            for linha in csv.DictReader(f):
                try:
                    v = float(linha["Tensao_Fonte_V"])
                    i = float(linha["Corrente_Filamento_A"])
                except (ValueError, KeyError, TypeError):
                    continue
                if v > 0.05 and i > 1e-3:
                    tensoes.append(v)
                    correntes.append(i)
    return np.array(tensoes), np.array(correntes)


def main():
    tensoes, correntes = carregar_pontos()
    if tensoes.size == 0:
        print("Nenhum CSV real encontrado em data_backup/.")
        return 1

    resistencias = tensoes / correntes
    potencias = tensoes * correntes
    temperaturas = np.array([temperatura_de(r) for r in resistencias])

    validos = (np.isfinite(temperaturas) & (temperaturas > T_AMBIENTE + 50)
               & (resistencias < 50))
    temperaturas = temperaturas[validos]
    potencias = potencias[validos]

    print(f"Pontos úteis: {temperaturas.size} de {tensoes.size}")
    print(f"Faixa de temperatura: {temperaturas.min():.0f} a {temperaturas.max():.0f} K\n")

    # P = k_rad·(T⁴ − T0⁴) + k_cond·(T − T0) — linear nos dois coeficientes.
    matriz = np.vstack([temperaturas ** 4 - T_AMBIENTE ** 4,
                        temperaturas - T_AMBIENTE]).T
    (k_rad, k_cond), *_ = np.linalg.lstsq(matriz, potencias, rcond=None)
    ajustada = matriz @ np.array([k_rad, k_cond])
    residuo = np.abs(ajustada - potencias) / potencias

    print(f"k_rad  = {k_rad:.6e} W/K⁴")
    print(f"k_cond = {k_cond:.6e} W/K")
    print(f"RAZAO_COND_RAD = {k_cond / k_rad:.5e}   <- é este o valor em mock_hardware.py\n")

    print(f"Resíduo relativo em potência: mediana {np.median(residuo)*100:.2f}%, "
          f"p95 {np.percentile(residuo, 95)*100:.2f}%")

    fracao_radiativa = (k_rad * (2500 ** 4 - T_AMBIENTE ** 4) /
                        (k_rad * (2500 ** 4 - T_AMBIENTE ** 4) + k_cond * (2500 - T_AMBIENTE)))
    print(f"A 2500 K a radiação responde por {fracao_radiativa*100:.0f}% da dissipação "
          "(coerente com a física esperada).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
