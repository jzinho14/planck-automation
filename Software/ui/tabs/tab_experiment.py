# ui/tabs/tab_experiment.py
import os
import csv
import time
from datetime import datetime
import numpy as np

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
                               QLineEdit, QPushButton, QTabWidget, QLabel, QGroupBox,
                               QProgressBar, QMessageBox, QTextEdit, QFileDialog,
                               QComboBox)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont
import pyqtgraph as pg

from content.filamentos import PRESETS_FILAMENTO, PRESET_PADRAO
from utils.math_models import (calculate_temperature, calculate_planck_constant,
                               corrigir_r0_para_zero_celsius, selecionar_pontos_validos,
                               TEMPERATURA_AMBIENTE_PADRAO, TEMPERATURA_MINIMA_PADRAO)
from core.hardware_manager import (obter_drivers, preferencias,
                                   CHAVE_MODO_DEMONSTRACAO,
                                   STRING_RECURSO_PWS, STRING_RECURSO_DMM)
import pyvisa
from ui.components.export_dialog import ExportDialog
from utils.pdf_exporter import generate_planck_report

# --- THREAD DE EXPERIMENTO REAL ---
class ExperimentWorker(QThread):
    new_data_point = Signal(float, float, float) # Tensão(V), Temperatura(K), Fotocorrente(A)
    finished_exp = Signal(float, float, float, float, float) # h, erro, m, c, r2
    error_occurred = Signal(str)
    
    def __init__(self, params, dmm_res, pws_res, modo_demonstracao: bool = False):
        super().__init__()
        self.params = params
        self.dmm_res = dmm_res
        self.pws_res = pws_res
        self.modo_demonstracao = modo_demonstracao
        self.is_running = True

        # Setup do ficheiro de backup (Fail-Safe). Coletas simuladas usam outro
        # prefixo: data_backup/ é o acervo de medidas reais e não pode receber
        # dados de demonstração sem aviso.
        os.makedirs("data_backup", exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        prefixo = "demo_planck" if modo_demonstracao else "exp_planck"
        self.csv_filename = f"data_backup/{prefixo}_{timestamp}.csv"

    def run(self):
        # Em modo demonstração não se abre o ResourceManager: os drivers
        # simulados têm a mesma interface e ignoram o argumento.
        ClasseFonte, ClasseMultimetro = obter_drivers(self.modo_demonstracao)
        rm = None if self.modo_demonstracao else pyvisa.ResourceManager('@ivi')
        pws = None
        dmm = None

        try:
            # 1. Inicializar os Drivers SCPI
            pws = ClasseFonte(rm, self.pws_res)
            dmm = ClasseMultimetro(rm, self.dmm_res)

            # Configurações de Segurança e Precisão
            pws.configure_safety_limits(max_current=2.0) # Limite de 1.5A para o filamento
            dmm.configure_dc_current(nplc=10.0) # Alta filtragem de ruído (60Hz)
            
            # Inicializar o ficheiro CSV com cabeçalho. As cinco primeiras
            # colunas são as históricas, na mesma ordem: arquivos antigos
            # continuam legíveis e leitores posicionais não quebram. A tensão
            # medida entra ao final, como rastreabilidade da correção A4.
            with open(self.csv_filename, mode='w', newline='') as file:
                writer = csv.writer(file)
                writer.writerow(["Tensao_Fonte_V", "Corrente_Filamento_A", "Resistencia_Ohms",
                                 "Temperatura_K", "Fotocorrente_A", "Tensao_Medida_V"])

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

                # A4: usar a tensão medida nos terminais, não o setpoint. Se o
                # instrumento não responder ao readback, cai para o valor
                # programado em vez de abortar a coleta.
                try:
                    v_medido = pws.measure_voltage()
                except Exception:
                    v_medido = v_target

                # Prevenir divisão por zero na resistência
                if i_fil < 1e-6:
                    i_fil = 1e-6

                # A4: a medição é a 2 fios, então a resistência dos cabos entra
                # no valor lido e precisa ser descontada.
                r_fil = v_medido / i_fil - self.params['r_cabos']

                # Calcular a Temperatura exata do instante usando Bhaskara
                t_array = calculate_temperature(np.array([r_fil]), self.params['r0'], self.params['alpha'], self.params['beta'])
                t_inst = t_array[0]

                # Guardar no Fail-Safe instantaneamente
                with open(self.csv_filename, mode='a', newline='') as file:
                    writer = csv.writer(file)
                    writer.writerow([v_target, i_fil, r_fil, t_inst, i_led, v_medido])

                # Armazenar para o cálculo final
                data_T.append(t_inst)
                data_I_led.append(i_led)
                
                # Enviar para a Interface Gráfica
                self.new_data_point.emit(v_target, t_inst, i_led)
                
            # 3. Finalizar e Desligar Fonte
            if pws: pws.set_output(False)
            
            # Calcular a Constante de Planck com os dados recolhidos (mesmo se interrompido!)
            if len(data_T) > 2:
                h_exp, erro, m, c, r2 = calculate_planck_constant(
                    np.array(data_T), np.array(data_I_led), self.params['lam'],
                    t_minima=self.params['t_minima']
                )
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

        # A3: presets de coeficientes com fonte citada.
        self.combo_preset = QComboBox()
        for preset in PRESETS_FILAMENTO:
            self.combo_preset.addItem(preset.rotulo, preset)
        self.combo_preset.currentIndexChanged.connect(self.aplicar_preset_filamento)

        self.input_r_frio = QLineEdit("1.2")
        self.input_t_ambiente = QLineEdit(str(TEMPERATURA_AMBIENTE_PADRAO))
        self.input_alpha = QLineEdit(str(PRESET_PADRAO.alpha))
        self.input_beta = QLineEdit(str(PRESET_PADRAO.beta))
        self.input_lambda = QLineEdit("590")
        self.input_r_cabos = QLineEdit("0.0")

        self.input_r_frio.setToolTip(
            "Resistência do filamento medida frio, na temperatura ambiente.\n"
            "O software converte para R0 (a 0 °C) automaticamente."
        )
        self.input_t_ambiente.setToolTip(
            "Temperatura em que a resistência a frio foi medida.\n"
            "Sem isso, R0 fica ~13% deslocado e enviesa todas as temperaturas."
        )
        self.input_r_cabos.setToolTip(
            "Resistência dos cabos da medição a 2 fios, que entra somada à do\n"
            "filamento. Deixe 0 se não souber; meça curto-circuitando as pontas."
        )

        # Mostra o R0 corrigido conforme o operador digita.
        self.lbl_r0_corrigido = QLabel()
        self.lbl_r0_corrigido.setStyleSheet("color: #64B5F6; font-size: 11px;")
        for campo in (self.input_r_frio, self.input_t_ambiente,
                      self.input_alpha, self.input_beta):
            campo.textChanged.connect(self.atualizar_r0_corrigido)

        form_params.addRow("Preset de coeficientes:", self.combo_preset)
        form_params.addRow("Resistência a frio medida (Ω):", self.input_r_frio)
        form_params.addRow("Temperatura ambiente (°C):", self.input_t_ambiente)
        form_params.addRow("", self.lbl_r0_corrigido)
        form_params.addRow("Coef. Linear α (K⁻¹):", self.input_alpha)
        form_params.addRow("Coef. Quadrático β (K⁻²):", self.input_beta)
        form_params.addRow("Comprimento de Onda λ (nm):", self.input_lambda)
        form_params.addRow("Resistência dos cabos (Ω):", self.input_r_cabos)
        group_params.setLayout(form_params)

        self.atualizar_r0_corrigido()

        group_sweep = QGroupBox("Varredura SCPI")
        form_sweep = QFormLayout()
        self.input_v_start = QLineEdit("1.0")
        self.input_v_end = QLineEdit("10.0")
        self.input_v_step = QLineEdit("0.5")
        self.input_delay = QLineEdit("3000") # 3 segundos para estabilização térmica real
        self.input_t_minima = QLineEdit(str(TEMPERATURA_MINIMA_PADRAO))
        self.input_t_minima.setToolTip(
            "Só entram na regressão os pontos acima desta temperatura.\n"
            "Abaixo dela a fotocorrente é menor que o ruído do multímetro.\n"
            "Varra a faixa que quiser: o CSV guarda tudo, o corte é só na conta."
        )
        form_sweep.addRow("Tensão Inicial (V):", self.input_v_start)
        form_sweep.addRow("Tensão Final (V):", self.input_v_end)
        form_sweep.addRow("Passo de Tensão (V):", self.input_v_step)
        form_sweep.addRow("Estabilização Térmica (ms):", self.input_delay)
        form_sweep.addRow("Temp. mínima p/ regressão (K):", self.input_t_minima)
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

    def aplicar_preset_filamento(self):
        """Preenche α e β com o preset escolhido (A3)."""
        preset = self.combo_preset.currentData()
        if preset is None:
            return
        self.input_alpha.setText(str(preset.alpha))
        self.input_beta.setText(str(preset.beta))
        self.combo_preset.setToolTip(f"Fonte: {preset.fonte}\n\n{preset.observacao}")

    def atualizar_r0_corrigido(self):
        """Mostra ao vivo o R0 que sai da correção da Eq. 11 (A2)."""
        try:
            r0 = corrigir_r0_para_zero_celsius(
                float(self.input_r_frio.text()),
                float(self.input_t_ambiente.text()),
                float(self.input_alpha.text()),
                float(self.input_beta.text()),
            )
        except (ValueError, ZeroDivisionError):
            self.lbl_r0_corrigido.setText("R0 a 0 °C: —  (verifique os valores)")
            return
        self.lbl_r0_corrigido.setText(
            f"→ R0 a 0 °C = {r0:.4f} Ω   (é este o valor usado no cálculo)"
        )

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
        self.plot_linear.addLegend(offset=(-10, 10))
        # Pontos descartados primeiro, para ficarem por baixo dos usados.
        self.scatter_descartado = pg.ScatterPlotItem(
            size=6, pen=pg.mkPen(None), brush=pg.mkBrush(120, 120, 120, 150),
            name="Descartado (fora da região de Wien)")
        self.scatter_linear = pg.ScatterPlotItem(
            size=6, pen=pg.mkPen('w'), brush=pg.mkBrush(255, 0, 0, 200),
            name="Usado na regressão")
        self.plot_linear.addItem(self.scatter_descartado)
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
        
        # Atualiza gráfico logarítmico. Os pontos que a regressão vai usar
        # aparecem em vermelho; os descartados, em cinza — o operador vê na
        # hora o que está entrando na conta (A5).
        arr_t = np.array(self.data_t, dtype=float)
        arr_i = np.array(self.data_i_led, dtype=float)
        plotavel = (arr_i > 1e-12) & np.isfinite(arr_t) & (arr_t != 0)
        usados = selecionar_pontos_validos(arr_t, arr_i, self.params['t_minima'])
        descartados = plotavel & ~usados

        for cena, mascara in ((self.scatter_linear, usados),
                              (self.scatter_descartado, descartados)):
            if np.any(mascara):
                cena.setData(1 / arr_t[mascara], np.log(arr_i[mascara]))
            else:
                cena.setData([], [])

        # Atualiza o Histórico (Console do lado direito)
        # Assumimos i_fil = V / R_fil. Vamos recalcular I_fil aproximado só para display:
        r_fil = self.params['r0'] * (1 + self.params['alpha']*(t-273.15) + self.params['beta']*(t-273.15)**2)
        i_fil = v / r_fil if r_fil > 0 else 0

        marca = "" if usados[-1] else "  (fora da regressão)"
        log_line = f"{v:05.2f}V | {i_fil:04.2f}A | {t:06.1f}K | {i_led:.2e}A{marca}"
        self.history_log.append(log_line)
        self.history_log.verticalScrollBar().setValue(self.history_log.verticalScrollBar().maximum())
        
        self.progress_bar.setValue(len(self.data_v))
        self.lbl_status.setText(f"A guardar em: {self.worker.csv_filename.split('/')[-1]}")

    def start_experiment(self):
        # Vai buscar as strings de ligação gravadas no painel
        settings = preferencias()
        modo_demonstracao = settings.value(CHAVE_MODO_DEMONSTRACAO, False, type=bool)

        if modo_demonstracao:
            # A bancada simulada dispensa validação: os recursos são fixos.
            dmm_res, pws_res = STRING_RECURSO_DMM, STRING_RECURSO_PWS
        else:
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
        self.scatter_t.setData([], [])
        self.scatter_linear.setData([], [])
        self.scatter_descartado.setData([], [])
        
        alpha = float(self.input_alpha.text())
        beta = float(self.input_beta.text())
        t_ambiente = float(self.input_t_ambiente.text())
        r_frio = float(self.input_r_frio.text())

        try:
            # A2: a medida a frio é feita na temperatura ambiente; R0 é a 0 °C.
            r0 = corrigir_r0_para_zero_celsius(r_frio, t_ambiente, alpha, beta)
        except ValueError as erro:
            QMessageBox.warning(self, "Parâmetro inválido", str(erro))
            self.btn_start.setEnabled(True)
            self.btn_stop.setEnabled(False)
            return

        params = {
            'r0': r0, 'r_frio': r_frio, 't_ambiente': t_ambiente,
            'alpha': alpha, 'beta': beta, 'lam': float(self.input_lambda.text()),
            'r_cabos': float(self.input_r_cabos.text()),
            't_minima': float(self.input_t_minima.text()),
            'v_start': float(self.input_v_start.text()), 'v_end': float(self.input_v_end.text()),
            'v_step': float(self.input_v_step.text()), 'delay': float(self.input_delay.text())
        }

        self.params = params

        # O máximo da barra tem de vir do MESMO vetor que o worker vai percorrer.
        # Calcular por int((v_end - v_start)/v_step) + 1 diverge do np.arange por
        # aritmética de float: p.ex. 1.0 a 10.0 com passo 0.3 dá 32 pontos no
        # arange e 31 na fórmula — a barra chegava a 103% e nunca fechava certo.
        voltages = np.arange(params['v_start'], params['v_end'] + params['v_step'], params['v_step'])
        self.progress_bar.setMaximum(max(len(voltages), 1))
        self.progress_bar.setValue(0)
        
        if modo_demonstracao:
            self.lbl_h_result.setText("Recolha SIMULADA em curso (sem hardware)")
            self.lbl_h_result.setStyleSheet("background-color: #8d6e00; color: white; border-radius: 5px; padding: 10px;")
        else:
            self.lbl_h_result.setText("Recolha em curso... Não desligue a Fonte!")
            self.lbl_h_result.setStyleSheet("background-color: #8b0000; color: white; border-radius: 5px; padding: 10px;")

        self.worker = ExperimentWorker(params, dmm_res, pws_res, modo_demonstracao)
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
        
        n_usados = int(np.sum(selecionar_pontos_validos(
            np.array(self.data_t, dtype=float),
            np.array(self.data_i_led, dtype=float),
            self.params['t_minima'])))

        self.lbl_h_result.setText(f"h = {h_exp:.4e} J.s")
        self.lbl_h_result.setStyleSheet("background-color: #1e1e1e; color: #00ff00; border-radius: 5px; padding: 10px;")
        self.lbl_status.setText(
            f"Erro: {erro:.2f}% | R²: {r2:.4f} | "
            f"{n_usados} de {len(self.data_t)} pontos na regressão"
        )
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
                    n_usados = int(np.sum(selecionar_pontos_validos(
                        np.array(self.data_t, dtype=float),
                        np.array(self.data_i_led, dtype=float),
                        self.params['t_minima'])))
                    params_formatados = {
                        'Resistência a frio medida': f"{self.params['r_frio']} Ω a {self.params['t_ambiente']} °C",
                        'R0 corrigido (0 °C)': f"{self.params['r0']:.4f} Ω",
                        'Alpha': f"{self.params['alpha']} K⁻¹",
                        'Beta': f"{self.params['beta']} K⁻²",
                        'Comprimento de Onda': f"{self.params['lam']} nm",
                        'Resistência dos cabos': f"{self.params['r_cabos']} Ω",
                        'Varredura': f"De {self.params['v_start']}V a {self.params['v_end']}V (Passo: {self.params['v_step']}V)",
                        'Estabilização Térmica': f"{self.params['delay']} ms",
                        'Temp. mínima na regressão': f"{self.params['t_minima']} K",
                        'Pontos usados na regressão': f"{n_usados} de {len(self.data_t)}"
                    }
                    
                    # Gera o PDF usando as variáveis globais
                    generate_planck_report(file_path, self.last_results, params_formatados, meta_data, img_path)
                    
                    # Limpa a imagem temporária
                    if os.path.exists(img_path):
                        os.remove(img_path)
                        
                    QMessageBox.information(self, "Sucesso", "Relatório Físico PDF exportado com sucesso!")
                except Exception as e:
                    QMessageBox.critical(self, "Erro", f"Falha ao gerar PDF:\n{str(e)}")