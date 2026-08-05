"""
Testes da página de Análise: carregador e Stefan-Boltzmann (Fase 6).

    cd Software && python ../Tests/test_analise.py

Roda sobre os CSVs reais de data_backup/, que são a melhor prova disponível de
que o carregador aguenta as três gerações de formato.
"""
import os
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "Software"))

from core import carregador
from utils import stefan_boltzmann
from utils.stefan_boltzmann import EXPOENTE_TEORICO, TOLERANCIA_RELATIVA_PCT

FALHAS = []


def checa(condicao, descricao, detalhe=""):
    print(f"  [{'ok  ' if condicao else 'FALHA'}] {descricao}{'  -> ' + detalhe if detalhe else ''}")
    if not condicao:
        FALHAS.append(descricao)


print("1. Carregador sobre as coletas reais")

caminhos = carregador.listar()
checa(len(caminhos) > 0, "há coletas em data_backup/", f"{len(caminhos)} arquivos")

coletas, problemas = carregador.carregar_varias(caminhos)
checa(not problemas, "todas carregam sem erro", str(problemas[:2]))
checa(len(coletas) == len(caminhos), "nenhuma foi perdida no caminho")

exemplo = max(coletas, key=lambda c: c.n_pontos)
checa(exemplo.n_pontos > 10, "a maior coleta tem dados", f"{exemplo.n_pontos} pontos")
checa(exemplo.temperatura.size == exemplo.fotocorrente.size == exemplo.corrente.size,
      "todas as colunas têm o mesmo comprimento")
checa(np.all(np.isfinite(exemplo.tensao_fonte)), "a tensão veio numérica")

checa(exemplo.geracao == "histórica",
      "coletas antigas são reconhecidas como formato histórico", exemplo.geracao)
checa(not exemplo.tem_metadados, "e não têm metadados (é o buraco que a Fase 4 tapou)")
checa(exemplo.parametros_conhecidos() == {},
      "então não sabem dizer com que parâmetros foram obtidas")
checa(exemplo.tensao_medida is None,
      "nem têm a coluna de tensão medida, que só existe da Fase 2 em diante")

print("\n2. Compatibilidade entre gerações de formato")

pasta = Path(tempfile.mkdtemp(prefix="coletas_teste_"))

# Geração histórica: 5 colunas.
(pasta / "antiga.csv").write_text(
    "Tensao_Fonte_V,Corrente_Filamento_A,Resistencia_Ohms,Temperatura_K,Fotocorrente_A\n"
    "6.0,1.2,5.0,2000.0,1e-7\n8.0,1.4,5.7,2200.0,3e-7\n10.0,1.5,6.4,2400.0,6e-7\n",
    encoding="utf-8")

# Geração atual: 8 colunas.
(pasta / "nova.csv").write_text(
    "Tensao_Fonte_V,Corrente_Filamento_A,Resistencia_Ohms,Temperatura_K,"
    "Fotocorrente_A,Tensao_Medida_V,Desvio_Fotocorrente_A,N_Leituras\n"
    "6.0,1.2,5.0,2000.0,1e-7,6.01,2e-9,3\n"
    "8.0,1.4,5.7,2200.0,3e-7,8.02,3e-9,3\n"
    "10.0,1.5,6.4,2400.0,6e-7,10.01,4e-9,3\n",
    encoding="utf-8")

antiga = carregador.carregar(str(pasta / "antiga.csv"))
nova = carregador.carregar(str(pasta / "nova.csv"))

checa(antiga.geracao == "histórica" and nova.geracao == "Fase 3+",
      "as duas gerações são distinguidas", f"{antiga.geracao} / {nova.geracao}")
checa(np.allclose(antiga.temperatura, nova.temperatura),
      "e as cinco colunas comuns são lidas igual nas duas")
checa(nova.desvio_fotocorrente is not None and antiga.desvio_fotocorrente is None,
      "só a nova traz o desvio Tipo A")
checa(np.allclose(nova.potencia, nova.tensao_medida * nova.corrente),
      "a potência usa a tensão MEDIDA quando ela existe")
checa(np.allclose(antiga.potencia, antiga.tensao_fonte * antiga.corrente),
      "e a programada quando não existe")

# Colunas fora de ordem: a leitura é por nome, não por posição.
(pasta / "trocada.csv").write_text(
    "Fotocorrente_A,Temperatura_K,Tensao_Fonte_V,Corrente_Filamento_A,Resistencia_Ohms\n"
    "1e-7,2000.0,6.0,1.2,5.0\n3e-7,2200.0,8.0,1.4,5.7\n6e-7,2400.0,10.0,1.5,6.4\n",
    encoding="utf-8")
trocada = carregador.carregar(str(pasta / "trocada.csv"))
checa(np.allclose(trocada.temperatura, antiga.temperatura),
      "colunas fora de ordem ainda são lidas corretamente")

print("\n3. Robustez do carregador")

(pasta / "vazio.csv").write_text("", encoding="utf-8")
(pasta / "outro.csv").write_text("a,b\n1,2\n", encoding="utf-8")
(pasta / "sujo.csv").write_text(
    "Tensao_Fonte_V,Corrente_Filamento_A,Resistencia_Ohms,Temperatura_K,Fotocorrente_A\n"
    "6.0,1.2,5.0,2000.0,1e-7\n8.0,ruim,5.7,2200.0,3e-7\n10.0,1.5,6.4,2400.0,6e-7\n",
    encoding="utf-8")

for nome in ("vazio", "outro"):
    try:
        carregador.carregar(str(pasta / f"{nome}.csv"))
        checa(False, f"'{nome}.csv' deveria ser rejeitado")
    except ValueError:
        checa(True, f"'{nome}.csv' é rejeitado com mensagem clara")

sujo = carregador.carregar(str(pasta / "sujo.csv"))
checa(np.isnan(sujo.corrente[1]) and np.isfinite(sujo.corrente[0]),
      "valor ilegível vira NaN sem derrubar a linha inteira")

bons, ruins = carregador.carregar_varias(
    [str(pasta / "antiga.csv"), str(pasta / "vazio.csv"), str(pasta / "nova.csv")])
checa(len(bons) == 2 and len(ruins) == 1,
      "um arquivo ruim no meio não impede os outros de carregarem",
      f"{len(bons)} ok, {len(ruins)} com problema")

print("\n4. Stefan-Boltzmann: dados sintéticos com expoente conhecido")

temperaturas = np.linspace(1800, 2600, 40)
for expoente in (4.0, 3.5, 4.5):
    potencias = 1e-12 * temperaturas ** expoente
    resultado = stefan_boltzmann.verificar(temperaturas, potencias, 1800.0)
    checa(abs(resultado.expoente - expoente) < 1e-6,
          f"recupera exatamente o expoente {expoente} injetado",
          f"{resultado.expoente:.6f}")

potencias = 1e-12 * temperaturas ** 4.0
resultado = stefan_boltzmann.verificar(temperaturas, potencias, 1800.0)
checa(resultado.compativel and resultado.desvio_relativo < 1e-6,
      "e considera compatível com a lei", resultado.veredicto[:60])

resultado_ruim = stefan_boltzmann.verificar(
    temperaturas, 1e-12 * temperaturas ** 2.5, 1800.0)
checa(not resultado_ruim.compativel,
      "expoente 2,5 é corretamente reprovado",
      f"{resultado_ruim.expoente:.2f}, {resultado_ruim.desvio_relativo:.0f}% de 4")

print("\n5. Stefan-Boltzmann: o corte de temperatura importa")

# Mistura região quente (radiativa, expoente 4) com fria (condução, expoente 1).
t_fria = np.linspace(400, 1200, 30)
p_fria = 6e-5 * (t_fria - 298.15)          # perdas lineares
t_tudo = np.concatenate([t_fria, temperaturas])
p_tudo = np.concatenate([p_fria, potencias])

sem_corte = stefan_boltzmann.verificar(t_tudo, p_tudo, t_minima=0.0)
com_corte = stefan_boltzmann.verificar(t_tudo, p_tudo, t_minima=1800.0)
checa(abs(com_corte.expoente - 4.0) < abs(sem_corte.expoente - 4.0),
      "incluir a região fria afasta o expoente de 4",
      f"sem corte {sem_corte.expoente:.2f} · com corte {com_corte.expoente:.2f}")
checa(com_corte.n_pontos < com_corte.n_total,
      "e o corte descarta os pontos frios",
      f"{com_corte.n_pontos} de {com_corte.n_total}")

try:
    stefan_boltzmann.verificar(np.array([2000.0]), np.array([5.0]), 1800.0)
    checa(False, "com menos de 3 pontos, recusa")
except ValueError:
    checa(True, "com menos de 3 pontos, recusa")

print("\n6. Stefan-Boltzmann sobre a bancada real (A10)")

resultados = []
for coleta in coletas:
    tensao = coleta.tensao_medida if coleta.tensao_medida is not None else coleta.tensao_fonte
    try:
        resultados.append(stefan_boltzmann.verificar(
            coleta.temperatura, coleta.potencia, 1800.0,
            tensao=tensao, corrente=coleta.corrente))
    except ValueError:
        continue

checa(len(resultados) >= 10, "a verificação se aplica à maioria das coletas",
      f"{len(resultados)} de {len(coletas)}")

expoentes = np.array([r.expoente for r in resultados])
compativeis = sum(1 for r in resultados if r.compativel)
checa(compativeis / len(resultados) > 0.6,
      "a maioria verifica a lei dentro de 10% do expoente 4",
      f"{compativeis} de {len(resultados)}")
checa(np.median(expoentes) > EXPOENTE_TEORICO,
      "e o expoente mediano fica ACIMA de 4, como o tungstênio prevê "
      "(emissividade cresce com T)",
      f"mediana {np.median(expoentes):.2f}")
checa(np.median([r.r2 for r in resultados]) > 0.95,
      "com ajuste bem linear em log-log",
      f"R² mediano {np.median([r.r2 for r in resultados]):.4f}")

import shutil
shutil.rmtree(pasta, ignore_errors=True)

if FALHAS:
    print(f"\n{len(FALHAS)} FALHA(S): " + "; ".join(FALHAS))
    sys.exit(1)
print("\nTodos os testes de análise passaram.")
