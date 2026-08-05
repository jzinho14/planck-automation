"""
Teste ponta a ponta da interface, sem hardware.

    cd Software && python ../Tests/test_interface.py

Abre a janela real, liga o modo demonstração e roda um experimento completo
pela mesma via que o operador usaria. Cobre o que os testes de unidade não
alcançam: a fiação entre painel, worker, gráficos, CSV e metadados.

Consolida as verificações que foram feitas ao longo das Fases 0 a 4.
"""
import glob
import json
import os
import sys

from PySide6.QtWidgets import QApplication, QGroupBox, QPushButton
from PySide6.QtCore import QTimer

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "Software"))

from ui.main_window import MainWindow
from ui.theme import DARK_THEME
from core.mock_hardware import bancada_simulada
from core import metadados
from content.referencias import REFERENCIAS
from utils.math_models import TEMPERATURA_AMBIENTE_PADRAO

FALHAS = []


def checa(condicao, descricao, detalhe=""):
    print(f"  [{'ok  ' if condicao else 'FALHA'}] {descricao}{'  -> ' + detalhe if detalhe else ''}")
    if not condicao:
        FALHAS.append(descricao)


app = QApplication(sys.argv)
app.setStyle("Fusion")
app.setStyleSheet(DARK_THEME)

arquivos_antes = set(glob.glob("data_backup/*"))

janela = MainWindow()
janela.show()
abas = janela.main_tabs
painel_conexao = janela.connection_panel
experimento = janela.tab_experiment
simulacao = janela.tab_simulation

print("1. A janela monta")

checa(abas.count() == 4, "quatro abas", f"{abas.count()}")
checa(len({id(abas.widget(i)) for i in range(abas.count())}) == abas.count(),
      "sem widgets repetidos entre abas (B1)")
for i in range(abas.count()):
    print(f"       {i}: {abas.tabText(i)} -> {type(abas.widget(i)).__name__}")

fichas = janela.tab_references.findChildren(QGroupBox)
botoes_refs = janela.tab_references.findChildren(QPushButton)
checa(len(fichas) == len(REFERENCIAS),
      "a aba de Referências monta uma ficha por documento", f"{len(fichas)}")
checa(all(b.isEnabled() for b in botoes_refs),
      "e todos os PDFs de referência estão presentes")

print("\n2. Modo demonstração")

painel_conexao.chk_demo.setChecked(True)
recurso_fonte = painel_conexao.get_resource_string(painel_conexao.pws_combo)
checa(recurso_fonte.startswith("DEMO::"),
      "ligar o modo troca os recursos por simulados", recurso_fonte)
checa(painel_conexao.pws_status.text() == "🟡",
      "e o indicador fica amarelo")

print("\n3. Perfis alimentam o painel compartilhado (Fase 4)")

painel = experimento.painel
checa(type(painel) is type(simulacao.painel),
      "as duas abas usam o MESMO componente de parâmetros")
checa(painel.modo == "bancada" and simulacao.painel.modo == "simulacao",
      "cada uma em seu modo")
checa(hasattr(painel, "input_r_cabos") and not hasattr(simulacao.painel, "input_r_cabos"),
      "campos de hardware só aparecem na aba de bancada")
checa(painel.combo_led.count() >= 3 and painel.combo_filamento.count() >= 2,
      "perfis carregados",
      f"{painel.combo_led.count()} LEDs, {painel.combo_filamento.count()} filamentos")
checa(painel.lbl_avisos.text() == "", "sem avisos de perfil corrompido")

lambda_antes = painel.input_lambda.text()
painel.combo_led.setCurrentIndex(1)
checa(painel.input_lambda.text() != lambda_antes,
      "trocar o perfil de LED atualiza os campos",
      f"{lambda_antes} -> {painel.input_lambda.text()}")
painel.combo_led.setCurrentIndex(0)

print("\n4. Experimento completo, varrendo de 0 a 12 V")

# O filamento virtual tem R0 conhecido; o operador digita o que o ohmímetro
# leria na temperatura ambiente, e o software converte (A2).
r_frio = bancada_simulada().resistencia_a_frio(TEMPERATURA_AMBIENTE_PADRAO)
painel.input_r_frio.setText(f"{r_frio:.4f}")
painel.input_t_ambiente.setText(str(TEMPERATURA_AMBIENTE_PADRAO))
painel.input_v_start.setText("0.0")
painel.input_v_end.setText("12.0")
painel.input_v_step.setText("0.4")
painel.input_delay.setText("1")
painel.input_n_leituras.setText("2")
painel.input_t_minima.setText("1800")

checa("1.2000" in painel.lbl_r0.text(),
      "a correção de R0 (A2) recupera o valor real do filamento virtual",
      painel.lbl_r0.text())

resultado_final = {}


def ao_terminar(resultado):
    resultado_final["r"] = resultado
    print(f"       {resultado.texto}")
    print(f"       erro {resultado.erro_relativo:.2f}% | R² {resultado.ajuste.r2:.4f} "
          f"| χ²_red {resultado.ajuste.chi2_reduzido:.3f}")
    print(f"       {resultado.n_usados} de {resultado.n_total} pontos | "
          + " · ".join(f"{n} {p:.0f}%" for n, p in resultado.orcamento_ordenado()))
    QTimer.singleShot(300, app.quit)


experimento.start_experiment()
experimento.worker.finished_exp.connect(ao_terminar)
experimento.worker.error_occurred.connect(
    lambda e: (FALHAS.append(f"erro na coleta: {e}"), app.quit()))
QTimer.singleShot(150000, lambda: (FALHAS.append("timeout na coleta"), app.quit()))
app.exec()

resultado = resultado_final.get("r")
checa(resultado is not None, "a coleta terminou e produziu resultado")

if resultado:
    checa(5e-34 < resultado.h < 8e-34, "h em faixa física", f"{resultado.h:.4e}")
    checa(resultado.incerteza_expandida > 0, "com incerteza expandida declarada")
    checa(resultado.compativel_com_codata,
          "e compatível com a CODATA dentro da incerteza")
    checa(resultado.ajuste.r2 > 0.99, "ajuste linear na região de Wien",
          f"R²={resultado.ajuste.r2:.4f}")
    checa(0 < resultado.n_usados < resultado.n_total,
          "parte dos pontos foi descartada pelo corte (A5)",
          f"{resultado.n_total - resultado.n_usados} fora")
    checa(abs(sum(p for _, p in resultado.orcamento_ordenado()) - 100) < 1e-6,
          "o orçamento de incertezas fecha em 100%")

    barra = experimento.progress_bar
    checa(barra.value() == barra.maximum(),
          "a barra de progresso fechou certo (B7)",
          f"{barra.value()}/{barra.maximum()}")

    cinzas = experimento.scatter_descartado.getData()[0]
    checa(cinzas is not None and len(cinzas) > 0,
          "os pontos descartados aparecem em cinza no gráfico (A5)",
          f"{len(cinzas)} pontos")

print("\n5. Arquivos gravados")

novos = sorted(set(glob.glob("data_backup/*")) - arquivos_antes)
csvs = [n for n in novos if n.endswith(".csv")]
jsons = [n for n in novos if n.endswith(".json")]

checa(len(csvs) == 1 and len(jsons) == 1,
      "a coleta produziu um CSV e um JSON irmão",
      ", ".join(os.path.basename(n) for n in novos))
checa(all("demo_planck" in os.path.basename(n) for n in novos),
      "com prefixo de demonstração, separados do acervo real")

if csvs:
    with open(csvs[0], encoding="utf-8") as arquivo:
        cabecalho = arquivo.readline().strip().split(",")
    historicas = ["Tensao_Fonte_V", "Corrente_Filamento_A", "Resistencia_Ohms",
                  "Temperatura_K", "Fotocorrente_A"]
    checa(cabecalho[:5] == historicas,
          "as cinco colunas históricas seguem na mesma ordem")
    checa("Tensao_Medida_V" in cabecalho and "Desvio_Fotocorrente_A" in cabecalho,
          "e as colunas novas entraram ao final", f"{len(cabecalho)} colunas")

if jsons:
    meta = json.loads(open(jsons[0], encoding="utf-8").read())
    checa(meta["perfis"]["led"] and meta["perfis"]["filamento"],
          "os metadados registram os perfis usados (P5)",
          f"{meta['perfis']['led']} / {meta['perfis']['filamento']}")
    checa(meta["filamento_medido"]["r0_corrigido_ohm"] is not None,
          "e o R0 efetivamente usado no cálculo",
          f"{meta['filamento_medido']['r0_corrigido_ohm']:.4f} Ω")
    checa(meta["resultado"] is not None and meta["resultado"]["texto"],
          "e o resultado final com incerteza",
          meta["resultado"]["texto"] if meta["resultado"] else "")
    checa(meta["modo"] == "demonstracao", "e que a coleta foi simulada")

for arquivo in novos:
    os.remove(arquivo)
print(f"       ({len(novos)} arquivo(s) de teste removidos)")

if FALHAS:
    print(f"\n{len(FALHAS)} FALHA(S): " + "; ".join(FALHAS))
    sys.exit(1)
print("\nInterface verificada ponta a ponta.")
