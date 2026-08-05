from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
                               QLineEdit, QPushButton, QTabWidget, QLabel, QGroupBox,
                               QProgressBar, QMessageBox, QFileDialog, QComboBox)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont
import pyqtgraph as pg
import numpy as np
import time
import os
from utils.pdf_exporter import generate_planck_report
from utils.math_models import H_REF
from ui.components.export_dialog import ExportDialog


from ui.components.painel_parametros import PainelParametros
from content.perfis import especificacoes_de_instrumentos
from utils.math_models import simulate_experiment_data, selecionar_pontos_validos
from utils.error_models import analisar_experimento

# --- THREAD DE SIMULAÇÃO EM TEMPO REAL ---
class SimulationWorker(QThread):
    # Sinais para enviar dados para a interface principal
    new_data_point = Signal(float, float, float, float)  # V, i_fil, T, I_led
    finished_sim = Signal(object)   # ResultadoAnalise completo

    def __init__(self, params):
        super().__init__()
        self.params = params
        self.is_running = True

    def run(self):
        # 1. Construir o vetor de tensões
        v_start = self.params['v_start']
        v_end = self.params['v_end']
        v_step = self.params['v_step']
        delay = self.params['delay'] / 1000.0 # ms para segundos
        
        voltages = np.arange(v_start, v_end + v_step, v_step)
        
        # 2. Calcular a física vetorizada de uma vez (mais eficiente)
        V, I_fil, R_fil, T, I_led = simulate_experiment_data(
            voltages, 
            self.params['r0'], self.params['alpha'], 
            self.params['beta'], self.params['lam'], self.params['noise']
        )
        
        # 3. Emitir ponto a ponto para simular a varredura temporal do equipamento
        emitidos = 0
        for i in range(len(voltages)):
            if not self.is_running:
                break

            self.new_data_point.emit(V[i], I_fil[i], T[i], I_led[i])
            emitidos += 1
            time.sleep(delay) # Simula o tempo de aquisição do DMM/PWS

        # 4. Calcular a Constante de Planck com os dados gerados, pela mesma
        #    cadeia de incertezas que a bancada real usa.
        #
        # Duas correções aqui, ambas de comportamento ao PARAR no meio:
        #
        # - O resultado é emitido mesmo quando a coleta foi interrompida. Antes
        #   a condição exigia `is_running`, então parar no meio não emitia sinal
        #   nenhum: a interface ficava travada em "encerrando…" para sempre,
        #   esperando um sinal que nunca vinha.
        # - Só os pontos EFETIVAMENTE emitidos entram na conta. Antes analisava
        #   os vetores inteiros, incluindo pontos que a simulação nunca chegou
        #   a "medir" — um resultado sobre dados que o operador não viu.
        V, I_fil, I_led = V[:emitidos], I_fil[:emitidos], I_led[:emitidos]

        if emitidos > 2:
            try:
                resultado = analisar_experimento(
                    V, I_fil, I_led,
                    r0=self.params['r0'], alpha=self.params['alpha'],
                    beta=self.params['beta'], lambda_nm=self.params['lam'],
                    delta_lambda_nm=self.params['delta_lam'],
                    u_r0=self.params['u_r0'],
                    t_minima=self.params['t_minima'],
                    **{chave: espec for grandeza, chave in
                       (("fotocorrente", "spec_fotocorrente"),
                        ("tensao_fonte", "spec_tensao"),
                        ("corrente_fonte", "spec_corrente"))
                       for espec in [especificacoes_de_instrumentos().get(grandeza)]
                       if espec is not None})
            except ValueError:
                return
            self.finished_sim.emit(resultado)

    def stop(self):
        self.is_running = False


# --- INTERFACE DA ABA ---
class TabSimulation(QWidget):
    def __init__(self):
        super().__init__()
        self.worker = None
        # Arrays para armazenar os dados dinâmicos da captura
        self.data_v = []
        self.data_i_led = []
        self.data_t = []
        
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        self.tabs = QTabWidget()
        self.tab_config = QWidget()
        self.tab_results = QWidget()
        
        self.tabs.addTab(self.tab_config, "1. Parâmetros e Varredura")
        self.tabs.addTab(self.tab_results, "2. Coleta e Resultados")
        
        self.build_config_tab()
        self.build_results_tab()
        
        layout.addWidget(self.tabs)

    def build_config_tab(self):
        layout = QHBoxLayout(self.tab_config)

        # Mesmo componente da aba de bancada (Fase 4), em modo simulação.
        self.painel = PainelParametros(modo="simulacao")
        layout.addWidget(self.painel, stretch=3)

        layout_btns = QVBoxLayout()
        self.btn_simulate = QPushButton("▶ Iniciar Coleta Simulada")
        self.btn_simulate.setMinimumHeight(50)
        self.btn_simulate.setStyleSheet("font-weight: bold; background-color: #2e7d32; color: white;")
        self.btn_simulate.clicked.connect(self.start_simulation)

        self.btn_stop = QPushButton("⏹ Parar Coleta")
        self.btn_stop.setMinimumHeight(50)
        self.btn_stop.setStyleSheet("font-weight: bold; background-color: #c62828; color: white;")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop_simulation)

        layout_btns.addWidget(self.btn_simulate)
        layout_btns.addWidget(self.btn_stop)
        layout_btns.addStretch()
        layout.addLayout(layout_btns, stretch=1)

    def build_results_tab(self):
        layout = QVBoxLayout(self.tab_results)
        
        # Status Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        layout.addWidget(self.progress_bar)
        
        # Big Numbers
        card_layout = QHBoxLayout()
        self.lbl_h_result = QLabel("Aguardando coleta...")
        self.lbl_h_result.setFont(QFont("Arial", 16, QFont.Bold))
        self.lbl_h_result.setAlignment(Qt.AlignCenter)
        self.lbl_h_result.setStyleSheet("background-color: #2d2d2d; color: #a0a0a0; border-radius: 5px; padding: 10px;")
        
        self.lbl_error = QLabel("...")
        self.lbl_error.setFont(QFont("Arial", 14))
        self.lbl_error.setAlignment(Qt.AlignCenter)
        self.lbl_error.setStyleSheet("background-color: #2d2d2d; color: #a0a0a0; border-radius: 5px; padding: 10px;")
        
        card_layout.addWidget(self.lbl_h_result)
        card_layout.addWidget(self.lbl_error)
        
        self.btn_export = QPushButton("📄 Exportar Relatório PDF")
        self.btn_export.setMinimumHeight(45)
        self.btn_export.setStyleSheet("font-weight: bold; background-color: #1565c0; color: white; border-radius: 5px;")
        self.btn_export.setEnabled(False) # Só ativa quando a simulação acaba
        self.btn_export.clicked.connect(self.export_pdf)
        card_layout.addWidget(self.btn_export)
        
        # Gráficos em Tempo Real
        pg.setConfigOption('background', '#1e1e1e') # Fundo escuro para combinar com tema
        pg.setConfigOption('foreground', '#d4d4d4')
        self.graph_layout = pg.GraphicsLayoutWidget()
        
        self.plot_raw = self.graph_layout.addPlot(title="Monitor de Fotocorrente em Tempo Real")
        self.plot_raw.setLabel('left', "Fotocorrente (A)")
        self.plot_raw.setLabel('bottom', "Tensão da Fonte (V)")
        self.scatter_raw = pg.ScatterPlotItem(size=6, pen=pg.mkPen(None), brush=pg.mkBrush(0, 150, 255, 200))
        self.plot_raw.addItem(self.scatter_raw)
        
        self.plot_linear = self.graph_layout.addPlot(title="Linearização Instantânea: ln(I) vs 1/T")
        self.plot_linear.setLabel('left', "ln(I)")
        self.plot_linear.setLabel('bottom', "1/T (K⁻¹)")
        self.plot_linear.addLegend(offset=(-10, 10))
        self.scatter_descartado = pg.ScatterPlotItem(
            size=6, pen=pg.mkPen(None), brush=pg.mkBrush(120, 120, 120, 150),
            name="Descartado (fora da região de Wien)")
        self.scatter_linear = pg.ScatterPlotItem(
            size=6, pen=pg.mkPen(None), brush=pg.mkBrush(255, 100, 0, 200),
            name="Usado na regressão")
        self.line_fit = pg.PlotDataItem(pen=pg.mkPen('w', width=2, style=Qt.DashLine))
        self.plot_linear.addItem(self.scatter_descartado)
        self.plot_linear.addItem(self.scatter_linear)
        self.plot_linear.addItem(self.line_fit)
        
        layout.addLayout(card_layout)
        layout.addWidget(self.graph_layout)

    def start_simulation(self):
        # Transição de UI
        self.tabs.setCurrentIndex(1)
        self.btn_simulate.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.progress_bar.setValue(0)
        
        # Limpar dados antigos
        self.data_v.clear()
        self.data_i_led.clear()
        self.data_t.clear()
        self.scatter_raw.setData([], [])
        self.scatter_linear.setData([], [])
        self.scatter_descartado.setData([], [])
        self.line_fit.setData([], [])
        
        self.lbl_h_result.setText("Coletando Dados...")
        self.lbl_h_result.setStyleSheet("background-color: #1e1e1e; color: #00ff00; border-radius: 5px; padding: 10px;")
        
        try:
            params = self.painel.coletar()
        except ValueError as erro:
            QMessageBox.warning(self, "Parâmetro inválido", str(erro))
            self.btn_simulate.setEnabled(True)
            self.btn_stop.setEnabled(False)
            return
        self.params = params

        # Mesmo vetor de tensões que o SimulationWorker vai percorrer — ver B7.
        voltages = np.arange(params['v_start'], params['v_end'] + params['v_step'], params['v_step'])
        self.progress_bar.setMaximum(max(len(voltages), 1))

        # Iniciar a Thread
        self.worker = SimulationWorker(params)
        self.worker.new_data_point.connect(self.update_realtime_plots)
        self.worker.finished_sim.connect(self.simulation_finished)
        self.worker.start()

    def update_realtime_plots(self, v, i_fil, t, i_led):
        # Adicionar novo ponto aos arrays
        self.data_v.append(v)
        self.data_t.append(t)
        self.data_i_led.append(i_led)
        
        # Atualizar gráfico 1 (Dados Brutos)
        self.scatter_raw.setData(self.data_v, self.data_i_led)
        
        # Atualizar gráfico 2 (Linearizado): em laranja o que a regressão vai
        # usar, em cinza o que ficou fora da região de Wien (A5).
        arr_t = np.array(self.data_t, dtype=float)
        arr_i = np.array(self.data_i_led, dtype=float)
        plotavel = (arr_i > 1e-12) & np.isfinite(arr_t) & (arr_t != 0)
        usados = selecionar_pontos_validos(arr_t, arr_i, self.params['t_minima'])

        for cena, mascara in ((self.scatter_linear, usados),
                              (self.scatter_descartado, plotavel & ~usados)):
            if np.any(mascara):
                cena.setData(1 / arr_t[mascara], np.log(arr_i[mascara]))
            else:
                cena.setData([], [])

        self.progress_bar.setValue(len(self.data_v))

    def simulation_finished(self, resultado):
        self.btn_simulate.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.btn_export.setEnabled(True)

        self.last_analise = resultado
        m, c = resultado.ajuste.m, resultado.ajuste.c

        # Guarda os resultados
        self.last_results = {
            'h_ref': H_REF,
            'h_exp': resultado.h,
            'error': resultado.erro_relativo,
            'r2': resultado.ajuste.r2,
            'incerteza_expandida': resultado.incerteza_expandida,
            'k': resultado.k,
            'texto': resultado.texto,
            'chi2_reduzido': resultado.ajuste.chi2_reduzido,
            'orcamento': resultado.orcamento_ordenado(),
            'compativel': resultado.compativel_com_codata,
        }
        
        # Guarda todos os parâmetros usados para rastreabilidade
        arr_t = np.array(self.data_t, dtype=float)
        arr_i = np.array(self.data_i_led, dtype=float)
        usados = selecionar_pontos_validos(arr_t, arr_i, self.params['t_minima'])
        n_usados = int(np.sum(usados))

        self.last_params = {
            'Resistência a frio medida': f"{self.params['r_frio']} Ω a {self.params['t_ambiente']} °C",
            'R0 corrigido (0 °C)': f"{self.params['r0']:.4f} Ω",
            'Coef. Linear (α)': f"{self.params['alpha']:g} K⁻¹",
            'Coef. Quadrático (β)': f"{self.params['beta']:g} K⁻²",
            'Comprimento de onda (λ)': f"{self.params['lam']:g} ± {self.params['delta_lam']:g} nm",
            'Varredura (Tensão)': f"De {self.params['v_start']:g} V a {self.params['v_end']:g} V (Passo: {self.params['v_step']:g} V)",
            'Fator de Ruído Simulado': f"{self.params['noise']:g}",
            'Incerteza de R0 propagada': f"{self.params['u_r0']:.5f} Ω",
            'Temp. mínima na regressão': f"{self.params['t_minima']} K",
            'Pontos usados na regressão': f"{n_usados} de {len(self.data_t)}"
        }

        # A reta de ajuste só se estende sobre os pontos que a produziram.
        if np.any(usados):
            x_linear = 1 / arr_t[usados]
            x_fit = np.array([np.min(x_linear), np.max(x_linear)])
            self.line_fit.setData(x_fit, m * x_fit + c)

        orcamento = " · ".join(f"{nome} {pct:.0f}%"
                               for nome, pct in resultado.orcamento_ordenado())
        self.lbl_h_result.setText(f"h = {resultado.texto}")
        self.lbl_error.setText(
            f"Erro vs CODATA: {resultado.erro_relativo:.2f}% | "
            f"R²: {resultado.ajuste.r2:.4f} | χ²_red: {resultado.ajuste.chi2_reduzido:.2f}\n"
            f"{resultado.n_usados}/{resultado.n_total} pontos | Incerteza: {orcamento}"
        )

    def export_pdf(self):
        # 1. Abre a janela de Metadados
        dialog = ExportDialog(self)
        if dialog.exec(): # Só prossegue se o utilizador clicar em OK
            meta_data = dialog.get_data()
            
            # 2. Abre a janela do explorador de ficheiros do Sistema Operativo
            file_path, _ = QFileDialog.getSaveFileName(
                self, 
                "Salvar Relatório Analítico", 
                "Relatorio_Planck.pdf", 
                "PDF Files (*.pdf)"
            )
            
            if file_path:
                try:
                    img_path = "temp_graph.png"
                    pixmap = self.graph_layout.grab()
                    pixmap.save(img_path)
                    
                    # Passamos os resultados, parâmetros e os metadados inseridos
                    generate_planck_report(file_path, self.last_results, self.last_params, meta_data, img_path)
                    
                    if os.path.exists(img_path):
                        os.remove(img_path)
                        
                    QMessageBox.information(self, "Sucesso", "Relatório PDF exportado com sucesso!")
                except Exception as e:
                    QMessageBox.critical(self, "Erro", f"Falha ao gerar PDF:\n{str(e)}")
        
    def stop_simulation(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait() # Aguarda a thread fechar com segurança
            self.lbl_h_result.setText("Coleta Interrompida")
            self.btn_simulate.setEnabled(True)
            self.btn_stop.setEnabled(False)