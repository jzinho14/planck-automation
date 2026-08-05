from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, 
                               QLineEdit, QPushButton, QTabWidget, QLabel, QGroupBox, QProgressBar, QMessageBox, QFileDialog)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont
import pyqtgraph as pg
import numpy as np
import time
import os
from utils.pdf_exporter import generate_planck_report
from utils.math_models import H_REF
from ui.components.export_dialog import ExportDialog


from utils.math_models import simulate_experiment_data, calculate_planck_constant

# --- THREAD DE SIMULAÇÃO EM TEMPO REAL ---
class SimulationWorker(QThread):
    # Sinais para enviar dados para a interface principal
    new_data_point = Signal(float, float, float) # Tensão (V), Temperatura (K), Fotocorrente (A)
    finished_sim = Signal(float, float, float, float, float) # h, erro, m, c, r2

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
        for i in range(len(voltages)):
            if not self.is_running:
                break
            
            self.new_data_point.emit(V[i], T[i], I_led[i])
            time.sleep(delay) # Simula o tempo de aquisição do DMM/PWS
            
        # 4. Calcular a Constante de Planck com os dados gerados
        if self.is_running and len(voltages) > 2:
            h_exp, erro, m, c, r2 = calculate_planck_constant(T, I_led, self.params['lam'])
            self.finished_sim.emit(h_exp, erro, m, c, r2)

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
        
        # Lado Esquerdo: Parâmetros Físicos
        group_params = QGroupBox("Constantes do Filamento e Sensor")
        form_params = QFormLayout()
        self.input_r0 = QLineEdit("1.2")
        self.input_alpha = QLineEdit("5.23e-3")
        self.input_beta = QLineEdit("7.0e-7")
        self.input_lambda = QLineEdit("590")
        self.input_noise = QLineEdit("0.05")
        form_params.addRow("Resistência a Frio R0 (Ω):", self.input_r0)
        form_params.addRow("Coef. Linear α (K⁻¹):", self.input_alpha)
        form_params.addRow("Coef. Quadrático β (K⁻²):", self.input_beta)
        form_params.addRow("Comprimento de Onda λ (nm):", self.input_lambda)
        form_params.addRow("Fator de Ruído (0 a 1):", self.input_noise)
        group_params.setLayout(form_params)
        
        # Lado Direito: Parâmetros de Varredura (Setup do Equipamento)
        group_sweep = QGroupBox("Parâmetros de Varredura (Simulação VISA)")
        form_sweep = QFormLayout()
        self.input_v_start = QLineEdit("0.5")
        self.input_v_end = QLineEdit("12.0")
        self.input_v_step = QLineEdit("0.1")
        self.input_delay = QLineEdit("50") # 50 ms entre pontos
        form_sweep.addRow("Tensão Inicial (V):", self.input_v_start)
        form_sweep.addRow("Tensão Final (V):", self.input_v_end)
        form_sweep.addRow("Passo de Tensão (V):", self.input_v_step)
        form_sweep.addRow("Intervalo de Captura (ms):", self.input_delay)
        group_sweep.setLayout(form_sweep)
        
        # Botões
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
        
        layout.addWidget(group_params)
        layout.addWidget(group_sweep)
        layout.addLayout(layout_btns)

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
        self.scatter_linear = pg.ScatterPlotItem(size=6, pen=pg.mkPen(None), brush=pg.mkBrush(255, 100, 0, 200))
        self.line_fit = pg.PlotDataItem(pen=pg.mkPen('w', width=2, style=Qt.DashLine))
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
        self.line_fit.setData([], [])
        
        self.lbl_h_result.setText("Coletando Dados...")
        self.lbl_h_result.setStyleSheet("background-color: #1e1e1e; color: #00ff00; border-radius: 5px; padding: 10px;")
        
        # Dicionário de parâmetros
        params = {
            'r0': float(self.input_r0.text()),
            'alpha': float(self.input_alpha.text()),
            'beta': float(self.input_beta.text()),
            'lam': float(self.input_lambda.text()),
            'noise': float(self.input_noise.text()),
            'v_start': float(self.input_v_start.text()),
            'v_end': float(self.input_v_end.text()),
            'v_step': float(self.input_v_step.text()),
            'delay': float(self.input_delay.text())
        }
        
        self.progress_bar.setMaximum(int((params['v_end'] - params['v_start']) / params['v_step']) + 1)
        
        # Iniciar a Thread
        self.worker = SimulationWorker(params)
        self.worker.new_data_point.connect(self.update_realtime_plots)
        self.worker.finished_sim.connect(self.simulation_finished)
        self.worker.start()

    def update_realtime_plots(self, v, t, i_led):
        # Adicionar novo ponto aos arrays
        self.data_v.append(v)
        self.data_t.append(t)
        self.data_i_led.append(i_led)
        
        # Atualizar gráfico 1 (Dados Brutos)
        self.scatter_raw.setData(self.data_v, self.data_i_led)
        
        # Atualizar gráfico 2 (Linearizado) dinamicamente (Apenas log válido)
        valid = np.array(self.data_i_led) > 1e-12
        if np.any(valid):
            v_t = np.array(self.data_t)[valid]
            v_i = np.array(self.data_i_led)[valid]
            
            x_linear = 1 / v_t
            y_linear = np.log(v_i)
            self.scatter_linear.setData(x_linear, y_linear)
            
        self.progress_bar.setValue(len(self.data_v))

    def simulation_finished(self, h_exp, erro, m, c, r2):
        self.btn_simulate.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.btn_export.setEnabled(True)
        
        # Guarda os resultados
        self.last_results = {
            'h_ref': H_REF,
            'h_exp': h_exp,
            'error': erro,
            'r2': r2
        }
        
        # Guarda todos os parâmetros usados para rastreabilidade
        self.last_params = {
            'Resistência a frio (R0)': f"{self.input_r0.text()} Ω",
            'Coef. Linear (α)': f"{self.input_alpha.text()} K⁻¹",
            'Coef. Quadrático (β)': f"{self.input_beta.text()} K⁻²",
            'Comprimento de onda (λ)': f"{self.input_lambda.text()} nm",
            'Varredura (Tensão)': f"De {self.input_v_start.text()} V a {self.input_v_end.text()} V (Passo: {self.input_v_step.text()} V)",
            'Fator de Ruído Simulado': self.input_noise.text()
        }
        
        valid = np.array(self.data_i_led) > 1e-12
        x_linear = 1 / np.array(self.data_t)[valid]
        x_fit = np.array([np.min(x_linear), np.max(x_linear)])
        y_fit = m * x_fit + c
        self.line_fit.setData(x_fit, y_fit)
        
        self.lbl_h_result.setText(f"h = {h_exp:.4e} J.s")
        self.lbl_error.setText(f"Erro Relativo: {erro:.2f}% | R²: {r2:.4f}")

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