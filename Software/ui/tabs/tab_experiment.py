# ui/tabs/tab_experiment.py
import os
import csv
import time
from datetime import datetime
import numpy as np

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, 
                               QLineEdit, QPushButton, QTabWidget, QLabel, QGroupBox, 
                               QProgressBar, QMessageBox, QTextEdit, QFileDialog)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont
import pyqtgraph as pg

from utils.math_models import calculate_temperature, calculate_planck_constant
from core.hardware_manager import PWS4323_Driver, DMM4050_Driver
import pyvisa
from ui.components.export_dialog import ExportDialog
from utils.pdf_exporter import generate_planck_report

# --- THREAD DE EXPERIMENTO REAL ---
class ExperimentWorker(QThread):
    new_data_point = Signal(float, float, float) # Tensão(V), Temperatura(K), Fotocorrente(A)
    finished_exp = Signal(float, float, float, float, float) # h, erro, m, c, r2
    error_occurred = Signal(str)
    
    def __init__(self, params, dmm_res, pws_res):
        super().__init__()
        self.params = params
        self.dmm_res = dmm_res
        self.pws_res = pws_res
        self.is_running = True
        
        # Setup do ficheiro de backup (Fail-Safe)
        os.makedirs("data_backup", exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.csv_filename = f"data_backup/exp_planck_{timestamp}.csv"

    def run(self):
        rm = pyvisa.ResourceManager('@ivi')
        pws = None
        dmm = None
        
        try:
            # 1. Inicializar os Drivers SCPI
            pws = PWS4323_Driver(rm, self.pws_res)
            dmm = DMM4050_Driver(rm, self.dmm_res)
            
            # Configurações de Segurança e Precisão
            pws.configure_safety_limits(max_current=2.0) # Limite de 1.5A para o filamento
            dmm.configure_dc_current(nplc=10.0) # Alta filtragem de ruído (60Hz)
            
            # Inicializar o ficheiro CSV com cabeçalho
            with open(self.csv_filename, mode='w', newline='') as file:
                writer = csv.writer(file)
                writer.writerow(["Tensao_Fonte_V", "Corrente_Filamento_A", "Resistencia_Ohms", "Temperatura_K", "Fotocorrente_A"])
            
            v_start = self.params['v_start']
            v_end = self.params['v_end']
            v_step = self.params['v_step']
            delay_sec = self.params['delay'] / 1000.0
            
            voltages = np.arange(v_start, v_end + v_step, v_step)
            
            data_T = []
            data_I_led = []
            
            pws.set_output(True)
            
            # 2. O Loop de Coleta de Dados
            for v_target in voltages:
                if not self.is_running:
                    break
                    
                # Aplicar Tensão
                pws.set_voltage(v_target)
                
                # Aguardar a estabilização térmica do filamento
                time.sleep(delay_sec)
                
                # Ler dados reais
                i_fil = pws.measure_current()
                i_led = dmm.read_current()
                
                # Prevenir divisão por zero na resistência
                if i_fil < 1e-6:
                    i_fil = 1e-6
                    
                r_fil = v_target / i_fil
                
                # Calcular a Temperatura exata do instante usando Bhaskara
                t_array = calculate_temperature(np.array([r_fil]), self.params['r0'], self.params['alpha'], self.params['beta'])
                t_inst = t_array[0]
                
                # Guardar no Fail-Safe instantaneamente
                with open(self.csv_filename, mode='a', newline='') as file:
                    writer = csv.writer(file)
                    writer.writerow([v_target, i_fil, r_fil, t_inst, i_led])
                
                # Armazenar para o cálculo final
                data_T.append(t_inst)
                data_I_led.append(i_led)
                
                # Enviar para a Interface Gráfica
                self.new_data_point.emit(v_target, t_inst, i_led)
                
            # 3. Finalizar e Desligar Fonte
            if pws: pws.set_output(False)
            
            # Calcular a Constante de Planck com os dados recolhidos (mesmo se interrompido!)
            if len(data_T) > 2:
                h_exp, erro, m, c, r2 = calculate_planck_constant(np.array(data_T), np.array(data_I_led), self.params['lam'])
                self.finished_exp.emit(h_exp, erro, m, c, r2)
            elif not self.is_running:
                # Interrompido antes de ter 3 pontos (impossível fazer regressão)
                self.error_occurred.emit("Recolha parada antes de acumular pontos suficientes para a regressão linear (>2). Os dados brutos foram salvos no CSV.")
                
        except Exception as e:
            if pws: pws.set_output(False)
            self.error_occurred.emit(str(e))
        finally:
            if pws: 
                pws.turn_off_safely() # Zera a tensão e desliga a saída
                pws.close()
            if dmm: 
                dmm.close()

    def stop(self):
        self.is_running = False


# --- INTERFACE DA ABA DO EXPERIMENTO ---
class TabExperiment(QWidget):
    def __init__(self, hw_manager):
        super().__init__()
        self.hw_manager = hw_manager
        self.worker = None
        self.data_v, self.data_t, self.data_i_led = [], [], []
        
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        self.tabs = QTabWidget()
        self.tab_config = QWidget()
        self.tab_results = QWidget()
        
        self.tabs.addTab(self.tab_config, "1. Parâmetros Reais")
        self.tabs.addTab(self.tab_results, "2. Coleta na Bancada")
        
        self.build_config_tab()
        self.build_results_tab()
        
        layout.addWidget(self.tabs)

    def build_config_tab(self):
        layout = QHBoxLayout(self.tab_config)
        
        group_params = QGroupBox("Calibração Física do Filamento")
        form_params = QFormLayout()
        self.input_r0 = QLineEdit("1.2")
        self.input_alpha = QLineEdit("5.23e-3")
        self.input_beta = QLineEdit("7.0e-7")
        self.input_lambda = QLineEdit("590")
        form_params.addRow("Resistência a Frio R0 (Ω):", self.input_r0)
        form_params.addRow("Coef. Linear α (K⁻¹):", self.input_alpha)
        form_params.addRow("Coef. Quadrático β (K⁻²):", self.input_beta)
        form_params.addRow("Comprimento de Onda λ (nm):", self.input_lambda)
        group_params.setLayout(form_params)
        
        group_sweep = QGroupBox("Varredura SCPI")
        form_sweep = QFormLayout()
        self.input_v_start = QLineEdit("1.0")
        self.input_v_end = QLineEdit("10.0")
        self.input_v_step = QLineEdit("0.5")
        self.input_delay = QLineEdit("3000") # 3 segundos para estabilização térmica real
        form_sweep.addRow("Tensão Inicial (V):", self.input_v_start)
        form_sweep.addRow("Tensão Final (V):", self.input_v_end)
        form_sweep.addRow("Passo de Tensão (V):", self.input_v_step)
        form_sweep.addRow("Estabilização Térmica (ms):", self.input_delay)
        group_sweep.setLayout(form_sweep)
        
        layout_btns = QVBoxLayout()
        self.btn_start = QPushButton("▶ Iniciar Experimento Físico")
        self.btn_start.setMinimumHeight(50)
        self.btn_start.setStyleSheet("font-weight: bold; background-color: #8b0000; color: white;")
        self.btn_start.clicked.connect(self.start_experiment)
        
        self.btn_stop = QPushButton("⏹ Parar e Processar Experimento")
        self.btn_stop.setMinimumHeight(50)
        self.btn_stop.setStyleSheet("font-weight: bold; background-color: #d84315; color: white;")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop_experiment)
        
        layout_btns.addWidget(self.btn_start)
        layout_btns.addWidget(self.btn_stop)
        layout_btns.addStretch()
        
        layout.addWidget(group_params)
        layout.addWidget(group_sweep)
        layout.addLayout(layout_btns)

    def build_results_tab(self):
        layout = QVBoxLayout(self.tab_results)
        
        self.progress_bar = QProgressBar()
        layout.addWidget(self.progress_bar)
        
        # --- Big Numbers ---
        card_layout = QHBoxLayout()
        self.lbl_h_result = QLabel("Equipamento em Standby...")
        self.lbl_h_result.setFont(QFont("Arial", 16, QFont.Bold))
        self.lbl_h_result.setAlignment(Qt.AlignCenter)
        self.lbl_h_result.setStyleSheet("background-color: #2d2d2d; color: #a0a0a0; border-radius: 5px; padding: 10px;")
        
        self.lbl_status = QLabel("Aguardando Início")
        self.lbl_status.setFont(QFont("Arial", 14))
        self.lbl_status.setAlignment(Qt.AlignCenter)
        self.lbl_status.setStyleSheet("background-color: #2d2d2d; color: #a0a0a0; border-radius: 5px; padding: 10px;")
        
        card_layout.addWidget(self.lbl_h_result)
        card_layout.addWidget(self.lbl_status)
        layout.addLayout(card_layout)
        
        self.btn_export = QPushButton("📄 Exportar Relatório PDF")
        self.btn_export.setMinimumHeight(50)
        self.btn_export.setStyleSheet("font-weight: bold; background-color: #1565C0; color: white;")
        self.btn_export.setEnabled(False)
        self.btn_export.clicked.connect(self.export_pdf)
        
        layout.addWidget(self.btn_export)
        
        # --- Área Principal (Gráficos à esquerda, Histórico à direita) ---
        main_view_layout = QHBoxLayout()
        
        # 1. Gráficos PyQtGraph
        pg.setConfigOption('background', '#1e1e1e')
        pg.setConfigOption('foreground', '#d4d4d4')
        self.graph_layout = pg.GraphicsLayoutWidget()
        
        # Gráfico Tensão vs Temperatura
        self.plot_t = self.graph_layout.addPlot(title="Temperatura do Filamento (K)")
        self.plot_t.setLabel('left', "Temp (K)")
        self.scatter_t = pg.ScatterPlotItem(size=6, pen=pg.mkPen('w'), brush=pg.mkBrush(255, 165, 0, 200)) # Laranja
        self.plot_t.addItem(self.scatter_t)
        
        # Gráfico Tensão vs Fotocorrente
        self.plot_raw = self.graph_layout.addPlot(title="Fotocorrente Real (A)")
        self.plot_raw.setLabel('left', "Corrente (A)")
        self.scatter_raw = pg.ScatterPlotItem(size=6, pen=pg.mkPen('w'), brush=pg.mkBrush(0, 150, 255, 200)) # Azul
        self.plot_raw.addItem(self.scatter_raw)
        
        self.graph_layout.nextRow()
        
        # Gráfico Intermédio de Linearização
        self.plot_linear = self.graph_layout.addPlot(title="Linearização Instantânea ln(I) vs 1/T", colspan=2)
        self.plot_linear.setLabel('left', "ln(I)")
        self.plot_linear.setLabel('bottom', "1/T (K⁻¹)")
        self.scatter_linear = pg.ScatterPlotItem(size=6, pen=pg.mkPen('w'), brush=pg.mkBrush(255, 0, 0, 200)) # Vermelho
        self.plot_linear.addItem(self.scatter_linear)
        
        main_view_layout.addWidget(self.graph_layout, stretch=3)
        
        # 2. Histórico Contínuo (Consola Log)
        self.history_log = QTextEdit()
        self.history_log.setReadOnly(True)
        self.history_log.setMinimumWidth(300)
        self.history_log.setStyleSheet("background-color: #121212; color: #00ff00; font-family: Consolas, monospace; font-size: 11px;")
        self.history_log.append("=== REGISTO EM TEMPO REAL ===")
        self.history_log.append("V_fonte | I_fil | Temp(K) | I_foto(A)")
        self.history_log.append("-" * 40)
        
        main_view_layout.addWidget(self.history_log, stretch=1)
        
        layout.addLayout(main_view_layout)


    def update_plots(self, v, t, i_led):
        # Atualiza arrays de dados
        self.data_v.append(v)
        self.data_t.append(t)
        self.data_i_led.append(i_led)
        
        # Atualiza gráficos superiores
        self.scatter_t.setData(self.data_v, self.data_t)
        self.scatter_raw.setData(self.data_v, self.data_i_led)
        
        # Atualiza gráfico logarítmico (Filtrando ruído negativo ou zero)
        valid = np.array(self.data_i_led) > 1e-12
        if np.any(valid):
            v_t = np.array(self.data_t)[valid]
            v_i = np.array(self.data_i_led)[valid]
            x_linear = 1 / v_t
            y_linear = np.log(v_i)
            self.scatter_linear.setData(x_linear, y_linear)
            
        # Atualiza o Histórico (Console do lado direito)
        # Assumimos i_fil = V / R_fil. Vamos recalcular I_fil aproximado só para display:
        r_fil = self.params['r0'] * (1 + self.params['alpha']*(t-273.15) + self.params['beta']*(t-273.15)**2)
        i_fil = v / r_fil if r_fil > 0 else 0
        
        log_line = f"{v:05.2f}V | {i_fil:04.2f}A | {t:06.1f}K | {i_led:.2e}A"
        self.history_log.append(log_line)
        self.history_log.verticalScrollBar().setValue(self.history_log.verticalScrollBar().maximum())
        
        self.progress_bar.setValue(len(self.data_v))
        self.lbl_status.setText(f"A guardar em: {self.worker.csv_filename.split('/')[-1]}")

    def start_experiment(self):
        # Vai buscar as strings de ligação gravadas no painel
        from PySide6.QtCore import QSettings
        settings = QSettings("Senac", "PlanckAutomation")
        dmm_res = settings.value("Connection/LastDMMRes", "")
        pws_res = settings.value("Connection/LastPWSRes", "")
        
        if not dmm_res or not pws_res:
            QMessageBox.warning(self, "Aviso", "Por favor, valide a ligação aos instrumentos no Painel de Hardware primeiro.")
            return

        self.tabs.setCurrentIndex(1)
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        
        self.data_v.clear(); self.data_t.clear(); self.data_i_led.clear()
        self.scatter_raw.setData([], [])
        
        params = {
            'r0': float(self.input_r0.text()), 'alpha': float(self.input_alpha.text()),
            'beta': float(self.input_beta.text()), 'lam': float(self.input_lambda.text()),
            'v_start': float(self.input_v_start.text()), 'v_end': float(self.input_v_end.text()),
            'v_step': float(self.input_v_step.text()), 'delay': float(self.input_delay.text())
        }
        
        self.params = params
        
        self.progress_bar.setMaximum(int((params['v_end'] - params['v_start']) / params['v_step']) + 1)
        self.progress_bar.setValue(0)
        
        self.lbl_h_result.setText("Recolha em curso... Não desligue a Fonte!")
        self.lbl_h_result.setStyleSheet("background-color: #8b0000; color: white; border-radius: 5px; padding: 10px;")
        
        self.worker = ExperimentWorker(params, dmm_res, pws_res)
        self.worker.new_data_point.connect(self.update_plots)
        self.worker.finished_exp.connect(self.experiment_finished)
        self.worker.error_occurred.connect(self.handle_error)
        self.worker.start()

    def experiment_finished(self, h_exp, erro, m, c, r2):
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.btn_export.setEnabled(True) # Habilita o botão do PDF
        
        # Salva os resultados para o PDF puxar depois
        self.last_results = {
            'h_ref': 6.626e-34,
            'h_exp': h_exp,
            'error': erro,
            'r2': r2
        }
        
        self.lbl_h_result.setText(f"h = {h_exp:.4e} J.s")
        self.lbl_h_result.setStyleSheet("background-color: #1e1e1e; color: #00ff00; border-radius: 5px; padding: 10px;")
        self.lbl_status.setText(f"Erro: {erro:.2f}% | Ficheiro Salvo.")
        QMessageBox.information(self, "Concluído", f"Experimento concluído em segurança.\nDados guardados em: {self.worker.csv_filename}")
        
        
    def handle_error(self, error_msg):
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.lbl_h_result.setText("Erro Crítico de I/O")
        QMessageBox.critical(self, "Erro no Equipamento VISA", error_msg)

    def stop_experiment(self):
        if self.worker and self.worker.isRunning():
            self.lbl_status.setText("A encerrar e a processar dados parciais...")
            self.btn_stop.setEnabled(False) # Previne duplo clique
            self.worker.stop() # Sinaliza a thread para quebrar o ciclo
            # Não fazemos .wait() aqui. A thread vai desligar a fonte, 
            # calcular os dados parciais e emitir finished_exp naturalmente.
            
    def export_pdf(self):
        # 1. Abre a janela de Metadados
        dialog = ExportDialog(self)
        if dialog.exec(): # Só prossegue se clicar em OK
            meta_data = dialog.get_data()
            
            # 2. Abre o explorador de ficheiros
            file_path, _ = QFileDialog.getSaveFileName(
                self, 
                "Salvar Relatório de Bancada", 
                "Relatorio_Bancada_Planck.pdf", 
                "PDF Files (*.pdf)"
            )
            
            if file_path:
                try:
                    # Captura a tela dos gráficos
                    img_path = "temp_bancada_graph.png"
                    pixmap = self.graph_layout.grab()
                    pixmap.save(img_path)
                    
                    # Formata os parâmetros reais usados para o relatório
                    params_formatados = {
                        'R0 (Frio)': f"{self.params['r0']} Ω",
                        'Alpha': f"{self.params['alpha']} K⁻¹",
                        'Beta': f"{self.params['beta']} K⁻²",
                        'Comprimento de Onda': f"{self.params['lam']} nm",
                        'Varredura': f"De {self.params['v_start']}V a {self.params['v_end']}V (Passo: {self.params['v_step']}V)",
                        'Estabilização Térmica': f"{self.params['delay']} ms"
                    }
                    
                    # Gera o PDF usando as variáveis globais
                    generate_planck_report(file_path, self.last_results, params_formatados, meta_data, img_path)
                    
                    # Limpa a imagem temporária
                    if os.path.exists(img_path):
                        os.remove(img_path)
                        
                    QMessageBox.information(self, "Sucesso", "Relatório Físico PDF exportado com sucesso!")
                except Exception as e:
                    QMessageBox.critical(self, "Erro", f"Falha ao gerar PDF:\n{str(e)}")