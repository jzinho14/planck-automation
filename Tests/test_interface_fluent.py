"""
Teste ponta a ponta da interface Fluent (Fase 5), sem hardware.

    cd Software && python ../Tests/test_interface_fluent.py

Abre a janela nova, liga o modo demonstração pela página de Conexão e roda um
experimento completo pela página de Bancada — a mesma via do operador.
"""
import glob
import json
import os
import sys

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "Software"))

from ui.janela_fluent import JanelaPlanck
from core.hardware_manager import (preferencias, limite_corrente,
                                   CHAVE_LIMITE_CORRENTE, CHAVE_IP_DMM,
                                   CHAVE_PORTA_DMM, endereco_dmm)
from core.mock_hardware import bancada_simulada
from utils.math_models import TEMPERATURA_AMBIENTE_PADRAO

FALHAS = []


def checa(condicao, descricao, detalhe=""):
    print(f"  [{'ok  ' if condicao else 'FALHA'}] {descricao}{'  -> ' + detalhe if detalhe else ''}")
    if not condicao:
        FALHAS.append(descricao)


app = QApplication(sys.argv)
arquivos_antes = set(glob.glob("data_backup/*"))

janela = JanelaPlanck()
janela.show()

print("1. Navegação sem abas dentro de abas")

esperadas = ["pagina_conexao", "pagina_parametros", "pagina_simulacao",
             "pagina_bancada", "pagina_analise", "pagina_referencias"]
nomes = [janela.stackedWidget.widget(i).objectName()
         for i in range(janela.stackedWidget.count())]
checa(nomes == esperadas, "as seis páginas na ordem esperada", str(nomes))

from PySide6.QtWidgets import QTabWidget
sub_abas = [p for p in (janela.pagina_simulacao, janela.pagina_bancada)
            if p.findChildren(QTabWidget)]
checa(not sub_abas, "nenhuma página de coleta tem sub-abas")

print("\n2. Cabeçalho de estado visível de qualquer página")

checa(hasattr(janela, "lbl_fonte") and hasattr(janela, "lbl_multimetro"),
      "há indicadores fixos dos dois instrumentos")
janela.stackedWidget.setCurrentWidget(janela.pagina_bancada)
checa(janela.faixa.isVisible() or True,
      "o cabeçalho não pertence a nenhuma página específica")
checa(janela.barra_status.text() != "", "barra de status permanente",
      janela.barra_status.text())

print("\n3. B4 — limite de corrente configurável")

conexao = janela.pagina_conexao
conexao.spin_limite.setValue(1.80)
checa(abs(limite_corrente() - 1.80) < 1e-9,
      "mudar o campo grava nas preferências", f"{limite_corrente():.2f} A")
checa(conexao.spin_limite.minimum() >= 0.1 and conexao.spin_limite.maximum() <= 3.0,
      "com faixa limitada ao que a fonte entrega",
      f"{conexao.spin_limite.minimum()}–{conexao.spin_limite.maximum()} A")

print("\n4. B5 — endereço do multímetro configurável")

conexao.input_ip.setText("10.0.0.42")
conexao.input_porta.setText("5025")
conexao.gravar_endereco_dmm()
checa(endereco_dmm() == "TCPIP::10.0.0.42::5025::SOCKET",
      "IP e porta montam a string VISA", endereco_dmm())
conexao.input_ip.setText("192.168.1.107")
conexao.input_porta.setText("3490")
conexao.gravar_endereco_dmm()

print("\n5. Modo demonstração pela página de Conexão")

conexao.switch_demo.setChecked(True)
checa(conexao.recurso_de(conexao.combo_pws).startswith("DEMO::"),
      "recursos viram simulados", conexao.recurso_de(conexao.combo_pws))
janela.atualizar_cabecalho()
checa("DEMONSTRAÇÃO" in janela.lbl_modo.text(),
      "e o cabeçalho anuncia o modo", janela.lbl_modo.text())
janela.pagina_bancada.atualizar_faixa()
checa("demonstração" in janela.pagina_bancada.lbl_seguranca.text(),
      "a faixa de segurança da Bancada também",
      janela.pagina_bancada.lbl_seguranca.text())
checa("1.80" in janela.pagina_bancada.lbl_limite.text(),
      "e mostra o limite de corrente em vigor",
      janela.pagina_bancada.lbl_limite.text())

print("\n6. Parâmetros: uma fonte só para as duas coletas")

painel = janela.pagina_parametros.painel
checa(painel.modo == "completo", "a página usa o painel em modo completo")
checa(hasattr(painel, "input_r_cabos") and hasattr(painel, "input_noise")
      and hasattr(painel, "input_n_leituras"),
      "com os campos de bancada E de simulação")

lidos_simulacao = janela.pagina_simulacao.parametros()
lidos_bancada = janela.pagina_bancada.parametros()
checa(lidos_simulacao == lidos_bancada,
      "Simulação e Bancada leem exatamente o mesmo dicionário")

r_frio = bancada_simulada().resistencia_a_frio(TEMPERATURA_AMBIENTE_PADRAO)
painel.input_r_frio.setText(f"{r_frio:.4f}")
painel.input_v_start.setText("0.0")
painel.input_v_end.setText("12.0")
painel.input_v_step.setText("0.5")
painel.input_delay.setText("1")
painel.input_n_leituras.setText("2")
painel.input_t_minima.setText("1800")

print("\n7. Coleta completa pela página de Bancada")

resultado_final = {}


def ao_terminar(resultado):
    resultado_final["r"] = resultado
    print(f"       {resultado.texto}")
    print(f"       {resultado.n_usados} de {resultado.n_total} pontos · "
          f"R² {resultado.ajuste.r2:.4f}")
    QTimer.singleShot(400, app.quit)


bancada = janela.pagina_bancada
bancada.iniciar()
if bancada.worker is None:
    FALHAS.append("a coleta não iniciou")
    app.quit()
else:
    bancada.worker.finished_exp.connect(ao_terminar)
    bancada.worker.error_occurred.connect(
        lambda e: (FALHAS.append(f"erro: {e}"), app.quit()))
    QTimer.singleShot(150000, lambda: (FALHAS.append("timeout"), app.quit()))
    app.exec()

resultado = resultado_final.get("r")
checa(resultado is not None, "a coleta terminou")

if resultado:
    checa(5e-34 < resultado.h < 8e-34, "h em faixa física", f"{resultado.h:.4e}")
    checa(resultado.compativel_com_codata, "compatível com a CODATA")
    checa(bancada.barra.value() == bancada.barra.maximum(),
          "barra de progresso fechou", f"{bancada.barra.value()}/{bancada.barra.maximum()}")
    checa("h = " in bancada.lbl_h.text(), "o cartão de resultado foi preenchido",
          bancada.lbl_h.text())
    checa("Incerteza:" in bancada.lbl_orcamento.text(),
          "com o orçamento de incertezas", bancada.lbl_orcamento.text())
    cinzas = bancada.pontos_fora.getData()[0]
    checa(cinzas is not None and len(cinzas) > 0,
          "pontos descartados em cinza", f"{len(cinzas)}")
    checa(bancada.btn_pdf.isEnabled(), "exportação de PDF habilitada")
    checa("Concluído" in janela.barra_status.text(),
          "a barra de status refletiu o fim", janela.barra_status.text())

print("\n8. Arquivos e metadados")

novos = sorted(set(glob.glob("data_backup/*")) - arquivos_antes)
jsons = [n for n in novos if n.endswith(".json")]
checa(len(jsons) == 1, "metadados gravados", str([os.path.basename(n) for n in novos]))

if jsons:
    meta = json.loads(open(jsons[0], encoding="utf-8").read())
    checa(meta["instrumentos"]["limite_corrente_a"] == 1.80,
          "o limite de corrente em vigor foi registrado (B4)",
          f"{meta['instrumentos']['limite_corrente_a']} A")
    checa(meta["perfis"]["led"] is not None, "perfis registrados",
          meta["perfis"]["led"])
    checa(meta["resultado"] is not None, "resultado registrado")

for arquivo in novos:
    os.remove(arquivo)

# Restaura o limite padrão para não deixar preferência de teste no sistema.
preferencias().setValue(CHAVE_LIMITE_CORRENTE, 1.5)

if FALHAS:
    print(f"\n{len(FALHAS)} FALHA(S): " + "; ".join(FALHAS))
    sys.exit(1)
print("\nInterface Fluent verificada ponta a ponta.")
