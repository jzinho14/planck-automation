"""
Testes do sistema de perfis e dos metadados por coleta (Fase 4).

Roda sem hardware e sem pytest:

    cd Software && python ../Tests/test_perfis_metadados.py

Usa uma pasta temporária para não tocar nos perfis reais do usuário.
"""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "Software"))

from content import perfis as mod_perfis
from content.perfis import (PerfilLed, PerfilFilamento, PerfilVarredura,
                            PerfilInstrumento, PADROES)
from core import metadados

FALHAS = []


def checa(condicao, descricao, detalhe=""):
    print(f"  [{'ok  ' if condicao else 'FALHA'}] {descricao}{'  -> ' + detalhe if detalhe else ''}")
    if not condicao:
        FALHAS.append(descricao)


# Redireciona a pasta de perfis para um diretório descartável.
_temporaria = Path(tempfile.mkdtemp(prefix="perfis_teste_"))
mod_perfis.PASTA_PERFIS = _temporaria

print("1. Padrões embutidos: a rede de segurança")

for tipo in ("leds", "filamentos", "instrumentos", "varreduras"):
    lista = mod_perfis.carregar_perfis(tipo)
    checa(len(lista) > 0, f"'{tipo}' carrega mesmo sem arquivo JSON",
          f"{len(lista)} perfis padrão")

# Perfis que carregam CONSTANTE FÍSICA precisam de procedência. Varredura não:
# é escolha operacional do experimentador, não um valor a ser citado.
com_constante_fisica = [p for tipo in ("leds", "filamentos", "instrumentos")
                        for p in PADROES[tipo]]
checa(all(p.fonte and p.fonte.strip() for p in com_constante_fisica),
      "todo perfil com constante física declara a sua fonte",
      f"{len(com_constante_fisica)} perfis conferidos")
checa(not any(hasattr(p, "fonte") for p in PADROES["varreduras"]),
      "perfis de varredura não pedem fonte (são escolha operacional)")
checa(not any(hasattr(p, "fonte") for p in PADROES["completos"]),
      "nem os perfis completos, que guardam a escolha do operador")

print("\n1b. Perfil completo guarda TODOS os campos da página")

from content.perfis import PerfilCompleto
completo = PADROES["completos"][0]
esperados = {"r_frio", "u_r_frio", "t_ambiente", "alpha", "beta", "lambda_nm",
             "delta_lambda_nm", "r_cabos", "ruido", "v_start", "v_end",
             "v_step", "delay_ms", "n_leituras", "t_minima"}
presentes = set(completo.__dataclass_fields__)
faltando = esperados - presentes
checa(not faltando, "o perfil completo cobre física, sensor, bancada e varredura",
      f"{len(esperados)} campos" if not faltando else str(faltando))

mod_perfis.salvar_perfis("completos", list(PADROES["completos"]))
mod_perfis.acrescentar_perfil("completos", PerfilCompleto(nome="Meu ajuste", v_end=9.0))
recuperado = mod_perfis.perfil_por_nome("completos", "Meu ajuste")
checa(recuperado is not None and recuperado.v_end == 9.0,
      "um perfil personalizado sobrevive ao ciclo de gravação e leitura")

print("\n2. Gravação e releitura")

mod_perfis.escrever_padroes_se_ausente()
no_disco = {caminho.stem for caminho in _temporaria.glob("*.json")}
checa(no_disco == set(PADROES),
      "toda família de perfil acaba com o seu JSON no disco",
      ", ".join(sorted(no_disco)))

antes = mod_perfis.carregar_perfis("leds")
depois = mod_perfis.carregar_perfis("leds")
checa([p.nome for p in antes] == [p.nome for p in depois],
      "releitura devolve os mesmos perfis")
checa(all(isinstance(p, PerfilLed) for p in depois),
      "e com o tipo certo (dataclass, não dicionário)")

# Não sobrescrever edição do operador.
alvo = _temporaria / "leds.json"
personalizados = [PerfilLed("Só meu", 700.0, 20.0, "medido no lab")]
mod_perfis.salvar_perfis("leds", personalizados)
mod_perfis.escrever_padroes_se_ausente()
checa(len(mod_perfis.carregar_perfis("leds")) == 1,
      "escrever_padroes_se_ausente NÃO sobrescreve arquivo existente")

print("\n3. Acrescentar e substituir perfil")

mod_perfis.acrescentar_perfil("leds", PerfilLed("Outro", 450.0, 25.0, "teste"))
nomes = [p.nome for p in mod_perfis.carregar_perfis("leds")]
checa(nomes == ["Só meu", "Outro"], "acrescentar preserva os existentes", str(nomes))

mod_perfis.acrescentar_perfil("leds", PerfilLed("Outro", 455.0, 25.0, "corrigido"))
lista = mod_perfis.carregar_perfis("leds")
checa(len(lista) == 2 and any(p.lambda_nm == 455.0 for p in lista),
      "gravar com nome repetido substitui em vez de duplicar")

checa(mod_perfis.perfil_por_nome("leds", "Outro") is not None,
      "busca por nome encontra")
checa(mod_perfis.perfil_por_nome("leds", "inexistente") is None,
      "e devolve None quando não há")

print("\n4. Robustez: JSON quebrado não derruba a coleta")

mod_perfis._avisos.clear()
(_temporaria / "filamentos.json").write_text("{ isto não é JSON válido", encoding="utf-8")
lista = mod_perfis.carregar_perfis("filamentos")
checa(len(lista) == len(PADROES["filamentos"]),
      "JSON corrompido cai para os padrões", f"{len(lista)} perfis")
checa(len(mod_perfis.avisos()) > 0, "e registra o aviso para a UI mostrar",
      mod_perfis.avisos()[0][:70])

mod_perfis._avisos.clear()
(_temporaria / "filamentos.json").write_text(
    json.dumps([{"nome": "bom", "alpha": 1e-3, "beta": 1e-7, "fonte": "x"},
                {"nome": "faltando campos"}]), encoding="utf-8")
lista = mod_perfis.carregar_perfis("filamentos")
checa(len(lista) == 1 and lista[0].nome == "bom",
      "perfis com campos faltando são ignorados, os válidos ficam")
checa(any("ignorados" in a for a in mod_perfis.avisos()),
      "com aviso de quantos foram descartados")

mod_perfis._avisos.clear()
(_temporaria / "filamentos.json").write_text('{"nao": "e uma lista"}', encoding="utf-8")
checa(len(mod_perfis.carregar_perfis("filamentos")) == len(PADROES["filamentos"]),
      "arquivo que não é lista também cai para os padrões")

mod_perfis._avisos.clear()
(_temporaria / "filamentos.json").write_text("[]", encoding="utf-8")
checa(len(mod_perfis.carregar_perfis("filamentos")) == len(PADROES["filamentos"]),
      "lista vazia também")

try:
    mod_perfis.carregar_perfis("inexistente")
    checa(False, "tipo desconhecido levanta erro")
except KeyError:
    checa(True, "tipo desconhecido levanta erro")

print("\n5. Perfis de instrumento alimentam a teoria de erros")

mod_perfis.salvar_perfis("instrumentos", PADROES["instrumentos"])
especificacoes = mod_perfis.especificacoes_de_instrumentos()
checa(set(especificacoes) == {"fotocorrente", "tensao_fonte", "corrente_fonte"},
      "as três grandezas são mapeadas", str(sorted(especificacoes)))

from utils.error_models import DMM4050_CORRENTE_100UA
do_perfil = especificacoes["fotocorrente"]
checa(do_perfil.pct_leitura == DMM4050_CORRENTE_100UA.pct_leitura
      and do_perfil.termo_fixo == DMM4050_CORRENTE_100UA.termo_fixo,
      "o perfil padrão reproduz a especificação embutida do DMM4050",
      f"{do_perfil.termo_fixo:.1e} A de fundo")

# Trocar de multímetro é trocar o JSON.
mod_perfis.salvar_perfis("instrumentos", [
    PerfilInstrumento("Multímetro hipotético", "fotocorrente",
                      0.001, 100e-9, "A", "inventado para o teste")])
nova = mod_perfis.especificacoes_de_instrumentos()["fotocorrente"]
checa(nova.termo_fixo == 100e-9,
      "trocar o JSON troca a especificação usada no cálculo",
      f"{nova.termo_fixo:.1e} A")

triangular = PerfilInstrumento("T", "fotocorrente", 0.0, 1e-9, "A", "teste",
                               distribuicao="triangular")
checa(triangular.como_especificacao().divisor > DMM4050_CORRENTE_100UA.divisor,
      "distribuição triangular usa divisor maior que a retangular")

print("\n6. Metadados por coleta (P5)")

pasta_csv = Path(tempfile.mkdtemp(prefix="coleta_teste_"))
csv_falso = pasta_csv / "exp_planck_teste.csv"
csv_falso.write_text("cabecalho\n", encoding="utf-8")

parametros = {
    "perfil_led": "Amarelo 590 nm", "perfil_filamento": "Padrão do software",
    "perfil_varredura": "Bancada — padrão",
    "r_frio": 1.3574, "u_r_frio": 0.01, "t_ambiente": 25.0,
    "r0": 1.2, "u_r0": 0.0132, "alpha": 5.23e-3, "beta": 7.0e-7,
    "r_cabos": 0.05, "lam": 590.0, "delta_lam": 30.0,
    "v_start": 0.0, "v_end": 12.0, "v_step": 0.25, "delay": 3000.0,
    "n_leituras": 3, "t_minima": 1800.0,
}

bloco = metadados.montar_abertura(parametros, False, "TCPIP::x", "USB::y")
destino = metadados.gravar(str(csv_falso), bloco)
checa(destino is not None and destino.exists(),
      "o JSON é gravado ao lado do CSV", destino.name)
checa(destino.stem == csv_falso.stem,
      "com o mesmo nome-base do CSV, só mudando a extensão")

lido = metadados.ler(str(csv_falso))
checa(lido["perfis"]["led"] == "Amarelo 590 nm", "os perfis usados ficam registrados")
checa(lido["filamento_medido"]["r0_corrigido_ohm"] == 1.2
      and lido["filamento_medido"]["resistencia_a_frio_ohm"] == 1.3574,
      "a medida a frio E o R0 corrigido ficam ambos registrados",
      "é o que faltava para entender coletas antigas")
checa(lido["filamento_medido"]["temperatura_ambiente_c"] == 25.0,
      "com a temperatura em que a medida foi feita")
checa(lido["varredura"]["leituras_por_ponto"] == 3, "e os parâmetros de varredura")
checa(lido["modo"] == "bancada_real", "o modo (real ou demonstração) é explícito")
checa(lido["resultado"] is None, "resultado começa vazio (coleta ainda em curso)")
checa("python" in lido["ambiente"], "o ambiente de execução é registrado")

checa(metadados.ler(str(pasta_csv / "nao_existe.csv")) == {},
      "ler coleta sem metadados devolve vazio, sem estourar")

(pasta_csv / "quebrado.json").write_text("{{{", encoding="utf-8")
checa(metadados.ler(str(pasta_csv / "quebrado.csv")) == {},
      "JSON corrompido também devolve vazio")

print("\n7. Metadados: bloco de resultado")


class _AjusteFalso:
    m, u_m, c, u_c = -24000.0, 600.0, 60.0, 0.3
    r2, chi2_reduzido, iteracoes = 0.9989, 0.101, 4


class _ResultadoFalso:
    h, u_h, incerteza_expandida, k = 6.5e-34, 2.6e-35, 5.2e-35, 2.0
    erro_relativo, compativel_com_codata = 1.88, True
    ajuste = _AjusteFalso()
    n_total, n_usados = 31, 18
    orcamento_temperatura = {"R": 4.4, "R0": 95.6}
    h_nao_ponderado = 6.29e-34
    texto = "(6,50 ± 0,52)×10^-34 J·s (k=2)"

    def orcamento_ordenado(self):
        return [("lambda", 53.0), ("inclinacao (aleatório)", 40.6), ("R0", 6.4)]


bloco["resultado"] = metadados.montar_resultado(_ResultadoFalso())
metadados.gravar(str(csv_falso), bloco)
lido = metadados.ler(str(csv_falso))
r = lido["resultado"]

checa(r["h_j_s"] == 6.5e-34 and r["incerteza_expandida_j_s"] == 5.2e-35,
      "h e a incerteza expandida são gravados")
checa(r["ajuste"]["chi2_reduzido"] == 0.101 and r["ajuste"]["iteracoes"] == 4,
      "com os diagnósticos do ajuste")
checa(r["orcamento_incerteza_h_pct"]["lambda"] == 53.0,
      "e o orçamento de incertezas completo")
checa(r["pontos"] == {"coletados": 31, "usados_na_regressao": 18},
      "e a contagem de pontos usados")
checa(r["compativel_com_codata"] is True,
      "o veredicto de compatibilidade é serializado como booleano")

# Tudo tem de ser JSON puro, sem tipos que só o Python entende.
texto = destino.read_text(encoding="utf-8")
json.loads(texto)
checa(True, "o arquivo final é JSON válido", f"{len(texto)} bytes")

shutil.rmtree(_temporaria, ignore_errors=True)
shutil.rmtree(pasta_csv, ignore_errors=True)

if FALHAS:
    print(f"\n{len(FALHAS)} FALHA(S): " + "; ".join(FALHAS))
    sys.exit(1)
print("\nTodos os testes de perfis e metadados passaram.")
