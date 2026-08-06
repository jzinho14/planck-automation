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

from PySide6.QtWidgets import QApplication, QScrollArea
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "Software"))

from ui import paleta
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
janela.mostrar()

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

print("\n2. Geometria: a janela precisa caber e ser arrastável")

app.processEvents()
disponivel = app.primaryScreen().availableGeometry()
checa(janela.isMaximized(), "abre maximizada, ocupando a área útil")

# A regressão que motivou este bloco: a janela nasceu com só o canto inferior
# esquerdo na tela. Sem moldura, isso a torna impossível de arrastar de volta.
# Verificamos o estado RESTAURADO, que é o que o botão de restaurar devolve.
janela.showNormal()
app.processEvents()
moldura = janela.frameGeometry()
checa(moldura.width() <= disponivel.width()
      and moldura.height() <= disponivel.height(),
      "restaurada, cabe inteira na área útil",
      f"{moldura.width()}x{moldura.height()} numa tela de "
      f"{disponivel.width()}x{disponivel.height()}")
checa(janela._dentro_da_tela(),
      "e com o canto superior esquerdo visível — logo, arrastável",
      f"({moldura.x()},{moldura.y()})")

alturas = {janela.stackedWidget.widget(i).objectName():
           janela.stackedWidget.widget(i).minimumSizeHint().height()
           for i in range(janela.stackedWidget.count())}
mais_alta = max(alturas, key=alturas.get)
checa(alturas[mais_alta] < 620,
      "nenhuma página exige mais altura que uma tela pequena",
      f"maior mínimo: {mais_alta} com {alturas[mais_alta]} px")

janela.showMaximized()
app.processEvents()

print("\n2b. Estado dos instrumentos, discreto e sempre visível")

checa(hasattr(janela, "lbl_estado"), "há um indicador de estado na barra de título")
checa(janela.lbl_estado.parent() is janela.titleBar,
      "e ele pertence à barra de título, não a nenhuma página")

# A regressão que motivou este bloco: o cabeçalho foi inserido no
# widgetLayout, que é HORIZONTAL, e virou uma coluna que comia 80% da
# largura. As páginas têm de ficar com quase toda a área útil.
largura_janela = janela.width()
largura_paginas = janela.stackedWidget.width()
fracao = largura_paginas / largura_janela
checa(fracao > 0.6,
      "as páginas ocupam a maior parte da largura da janela",
      f"{largura_paginas} de {largura_janela} px ({fracao*100:.0f}%)")

altura_status = janela.barra_status.height()
checa(altura_status < janela.height() * 0.1,
      "a barra de status é uma faixa fina, não um painel",
      f"{altura_status} px de {janela.height()}")

checa(len(janela.lbl_estado.text()) < 60,
      "o texto de estado é curto — o detalhe fica no tooltip",
      repr(janela.lbl_estado.text()))
checa("VI_ERROR" not in janela.lbl_estado.text(),
      "mensagens cruas de erro VISA não vazam para a barra de título")

janela.stackedWidget.setCurrentWidget(janela.pagina_bancada)
app.processEvents()
checa(janela.stackedWidget.width() / janela.width() > 0.6,
      "e continuam ocupando, em qualquer página")
checa(janela.barra_status.text() != "", "barra de status permanente",
      janela.barra_status.text())

print("\n3. B4 — limite de corrente configurável")

conexao = janela.pagina_conexao
bancada_pg = janela.pagina_bancada
painel_cfg = janela.pagina_parametros.painel

checa(not hasattr(conexao, "spin_limite"),
      "o limite não está na página de Conexão")
checa(not hasattr(bancada_pg, "spin_limite"),
      "nem é editável na página de Bancada")
checa(hasattr(painel_cfg, "input_limite"),
      "ele mora em Parâmetros › Bancada — configuração num lugar só")

painel_cfg.input_limite.setText("1.8")
painel_cfg._gravar_limite()
checa(abs(limite_corrente() - 1.80) < 1e-9,
      "editar lá grava nas preferências", f"{limite_corrente():.2f} A")
checa(painel_cfg.coletar()["limite_corrente"] == 1.8,
      "e viaja com os demais parâmetros até o worker")

bancada_pg.atualizar_faixa()
checa("1.80" in bancada_pg.lbl_limite.text(),
      "a Bancada apenas EXIBE o valor em vigor, para conferência",
      bancada_pg.lbl_limite.text())
checa(all(hasattr(bancada_pg, n)
          for n in ("ind_tensao", "ind_corrente", "ind_potencia")),
      "e mostra tensão, corrente e potência ao vivo")

print("\n3b. Configuração em seções, com os catálogos junto dos campos")

checa(painel_cfg.secoes.count() == 5,
      "cinco seções de configuração", f"{painel_cfg.secoes.count()}")
checa(painel_cfg.combo_filamento.parent() is painel_cfg.secoes.widget(0),
      "o catálogo de filamento fica DENTRO da seção Filamento")
checa(painel_cfg.combo_led.parent() is painel_cfg.secoes.widget(1),
      "o de LED, dentro da seção Sensor")
checa(painel_cfg.combo_varredura.parent() is painel_cfg.secoes.widget(2),
      "o de varredura, dentro da seção Varredura")

print("\n3c. Gráficos: um por vez, com visão completa opcional")

checa(bancada_pg.pilha_graficos.count() == 3,
      "três gráficos empilhados, um visível por vez")
bancada_pg.seletor_grafico.setCurrentItem("linear")
app.processEvents()
checa(bancada_pg.pilha_graficos.currentIndex() == 2,
      "o seletor troca o gráfico exibido")
bancada_pg.seletor_grafico.setCurrentItem("temp")

bancada_pg.abrir_visao_completa()
app.processEvents()
checa(bancada_pg.visao_completa is not None
      and bancada_pg.visao_completa.isVisible(),
      "o botão 'Ver tudo' abre a janela com os três gráficos")
checa(len(bancada_pg.visao_completa.plots) == 3,
      "e ela traz os três, empilhados")
bancada_pg.visao_completa.close()

print("\n3d. Tema claro e escuro, alternáveis pela barra de título")

checa(paleta.TEMA_PADRAO == "claro", "quem nunca escolheu abre no tema claro",
      paleta.TEMA_PADRAO)
# O tema é preferência PERSISTIDA, então o teste parte de um estado conhecido
# em vez de supor que a máquina está no padrão de fábrica.
janela.aplicar_tema("claro")
app.processEvents()
claro_fundo = paleta.cor("grafico_fundo")
claro_tinta = paleta.cor("tinta")
checa(QColor(claro_fundo).lightness() > QColor(claro_tinta).lightness(),
      "no claro, o fundo do gráfico é mais claro que a tinta",
      f"fundo {claro_fundo} · tinta {claro_tinta}")

janela.alternar_tema()
app.processEvents()
checa(paleta.nome_tema() == "escuro", "o botão da barra de título alterna",
      paleta.nome_tema())

escuro_fundo = paleta.cor("grafico_fundo")
checa(QColor(escuro_fundo).lightness() < QColor(claro_fundo).lightness(),
      "e o escuro é de fato mais escuro", f"{claro_fundo} → {escuro_fundo}")
checa(QColor(escuro_fundo).lightness() > 20,
      "sem cair no preto puro, que era a queixa da interface antiga",
      f"luminosidade {QColor(escuro_fundo).lightness()}")

# O ponto que motivou `repintar_tema`: um gráfico criado antes da troca
# precisa ACOMPANHAR o tema novo, e não só os criados depois.
fundo_desenhado = bancada_pg.plot_temp.backgroundBrush().color()
checa(fundo_desenhado.name().lower() == escuro_fundo.lower(),
      "gráficos já na tela acompanham a troca",
      f"{fundo_desenhado.name()} vs {escuro_fundo}")
checa(escuro_fundo.lower() in bancada_pg.registro.styleSheet().lower()
      or paleta.cor("superficie_alt").lower() in bancada_pg.registro.styleSheet().lower(),
      "o painel de registro também")

# A página de Parâmetros é feita de widgets Qt comuns, que por padrão seguem o
# modo de cor do SISTEMA. Numa máquina com o Windows em modo escuro, isso
# deixava metade da interface clara e metade escura.
dicas = app.styleHints()
if hasattr(dicas, "setColorScheme"):
    checa(dicas.colorScheme() == Qt.ColorScheme.Dark,
          "widgets Qt comuns seguem o tema do software, não o do Windows",
          str(dicas.colorScheme()))


# A regressão que motivou este bloco: o esquema de cor era aplicado DEPOIS de
# setTheme, e cada repolimento congelava a paleta vigente. Os widgets nativos
# ficavam uma troca ATRASADOS — lista de coletas preta no tema claro, painel de
# referências branco no escuro. Aqui comparamos a paleta de widgets nativos de
# tres paginas diferentes com a da aplicacao, nos dois temas.
def conferir_paletas(rotulo):
    esperada = app.palette().base().color().name()
    # Só widgets que dependem da paleta NATIVA. O registro da coleta tem folha
    # de estilo própria (superfície recuada, de propósito) e é conferido acima.
    nativos = {
        "lista de coletas": janela.pagina_analise.lista,
        "campo de parâmetro": painel_cfg.input_r_frio,
        "rolagem de referências": janela.pagina_referencias.conteudo.findChild(
            QScrollArea).viewport(),
    }
    for nome, widget in nativos.items():
        obtida = widget.palette().base().color().name()
        checa(obtida == esperada, f"{rotulo}: {nome} usa a paleta em vigor",
              f"{obtida} vs {esperada}")


conferir_paletas("escuro")

janela.alternar_tema()
app.processEvents()
if hasattr(dicas, "setColorScheme"):
    checa(dicas.colorScheme() == Qt.ColorScheme.Light,
          "e voltam junto com ele")
checa(paleta.nome_tema() == "claro", "e volta ao claro no segundo clique")
conferir_paletas("claro")

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
checa("demonstração" in janela.lbl_estado.text(),
      "e a barra de título anuncia o modo", janela.lbl_estado.text())
janela.pagina_bancada.atualizar_faixa()
checa("emonstração" in janela.pagina_bancada.lbl_seguranca.text(),
      "a faixa de segurança da Bancada também",
      janela.pagina_bancada.lbl_seguranca.text())
checa("1.80" in janela.pagina_bancada.lbl_limite.text(),
      "e o limite em vigor aparece na faixa",
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
    checa("×" in bancada.destaque.lbl_valor.text(),
          "o número-herói traz o valor em potência de dez",
          bancada.destaque.lbl_valor.text())
    checa("±" in bancada.destaque.lbl_incerteza.text(),
          "e a incerteza logo abaixo dele",
          bancada.destaque.lbl_incerteza.text())
    checa(bancada.cartoes["erro"].lbl_valor.text() != "—",
          "os cartões de diagnóstico foram preenchidos",
          " · ".join(f"{nome} {c.lbl_valor.text()}"
                     for nome, c in bancada.cartoes.items()))
    checa(len(bancada.barra_orcamento._fatias) > 0,
          "a barra de orçamento recebeu as fatias",
          str([n for n, _ in bancada.barra_orcamento._fatias]))
    selo = bancada.destaque.selo
    checa("✓" in selo.lbl.text() or "⚠" in selo.lbl.text(),
          "o selo de veredicto traz ícone além da cor", selo.lbl.text())
    checa(bancada.ind_potencia.lbl_valor.text().endswith("W"),
          "e a potência ao vivo foi atualizada", bancada.ind_potencia.lbl_valor.text())
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
