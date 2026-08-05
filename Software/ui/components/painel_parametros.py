# ui/components/painel_parametros.py
"""
Painel de parâmetros compartilhado pelas abas de Simulação e de Bancada.

Antes da Fase 4 os mesmos campos existiam duplicados nas duas abas: mudar um
rótulo, um padrão ou uma unidade exigia lembrar de mudar nos dois lugares, e
os dois foram divergindo. Agora há um componente só, e cada aba escolhe o que
precisa mostrar.

O painel é um QWidget comum, então continua embutível quando a interface
migrar para páginas com cartões — só muda quem o hospeda.
"""
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QFormLayout, QGroupBox,
                               QLineEdit, QLabel, QComboBox, QPushButton,
                               QHBoxLayout, QInputDialog, QMessageBox)
from PySide6.QtCore import Signal

from content.perfis import (carregar_perfis, acrescentar_perfil, avisos,
                            PerfilVarredura)
from utils.math_models import (corrigir_r0_para_zero_celsius,
                               TEMPERATURA_AMBIENTE_PADRAO,
                               TEMPERATURA_MINIMA_PADRAO)
from utils.error_models import incerteza_r0_corrigido, INCERTEZA_TEMPERATURA_AMBIENTE


class PainelParametros(QWidget):
    """
    Campos de física e de varredura, alimentados por perfis.

    `modo` controla o que aparece:
      "bancada"   — inclui resistência de cabos e leituras por ponto
      "simulacao" — inclui fator de ruído, sem os campos de hardware
    """

    parametros_alterados = Signal()

    def __init__(self, modo: str = "bancada", parent=None):
        super().__init__(parent)
        self.modo = modo
        self._montar()
        self._recarregar_perfis()

    # -- construção ----------------------------------------------------------

    def _montar(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # --- Perfis ---
        grupo_perfis = QGroupBox("Perfis")
        form_perfis = QFormLayout()

        self.combo_led = QComboBox()
        self.combo_filamento = QComboBox()
        self.combo_varredura = QComboBox()
        self.combo_led.currentIndexChanged.connect(self._aplicar_led)
        self.combo_filamento.currentIndexChanged.connect(self._aplicar_filamento)
        self.combo_varredura.currentIndexChanged.connect(self._aplicar_varredura)

        form_perfis.addRow("LED (sensor):", self.combo_led)
        form_perfis.addRow("Filamento:", self.combo_filamento)
        form_perfis.addRow("Varredura:", self.combo_varredura)

        self.btn_salvar_varredura = QPushButton("💾 Salvar varredura atual como perfil")
        self.btn_salvar_varredura.clicked.connect(self._salvar_varredura)
        form_perfis.addRow("", self.btn_salvar_varredura)

        self.lbl_avisos = QLabel()
        self.lbl_avisos.setWordWrap(True)
        self.lbl_avisos.setStyleSheet("color: #ffb74d; font-size: 11px;")
        form_perfis.addRow("", self.lbl_avisos)

        grupo_perfis.setLayout(form_perfis)
        layout.addWidget(grupo_perfis)

        # --- Filamento medido nesta montagem ---
        grupo_fisica = QGroupBox("Filamento desta montagem")
        form_fisica = QFormLayout()

        self.input_r_frio = QLineEdit("1.2")
        self.input_u_r_frio = QLineEdit("0.01")
        self.input_t_ambiente = QLineEdit(str(TEMPERATURA_AMBIENTE_PADRAO))
        self.input_alpha = QLineEdit()
        self.input_beta = QLineEdit()
        self.input_lambda = QLineEdit()
        self.input_delta_lambda = QLineEdit()

        self.input_r_frio.setToolTip(
            "Resistência do filamento medida frio, na temperatura ambiente.\n"
            "Não é R0: o software converte para 0 °C automaticamente.")
        self.input_u_r_frio.setToolTip(
            "Incerteza da medida acima (o erro do ohmímetro).")
        self.input_t_ambiente.setToolTip(
            "Temperatura em que a resistência a frio foi medida.\n"
            "Errar aqui desloca TODAS as temperaturas calculadas.")
        self.input_delta_lambda.setToolTip(
            "Meia largura espectral do LED. É quase sempre a maior fonte\n"
            "de incerteza em h — vem do perfil, mas pode ser ajustada.")

        self.lbl_r0 = QLabel()
        self.lbl_r0.setStyleSheet("color: #64B5F6; font-size: 11px;")

        for campo in (self.input_r_frio, self.input_u_r_frio,
                      self.input_t_ambiente, self.input_alpha, self.input_beta):
            campo.textChanged.connect(self._atualizar_r0)

        form_fisica.addRow("Resistência a frio medida (Ω):", self.input_r_frio)
        form_fisica.addRow("Incerteza de R a frio (Ω):", self.input_u_r_frio)
        form_fisica.addRow("Temperatura ambiente (°C):", self.input_t_ambiente)
        form_fisica.addRow("", self.lbl_r0)
        form_fisica.addRow("Coef. Linear α (K⁻¹):", self.input_alpha)
        form_fisica.addRow("Coef. Quadrático β (K⁻²):", self.input_beta)
        form_fisica.addRow("Comprimento de Onda λ (nm):", self.input_lambda)
        form_fisica.addRow("Largura espectral Δλ (nm):", self.input_delta_lambda)

        if self.modo == "bancada":
            self.input_r_cabos = QLineEdit("0.0")
            self.input_r_cabos.setToolTip(
                "Resistência dos cabos da medição a 2 fios, descontada de R.\n"
                "Meça curto-circuitando as pontas; deixe 0 se não souber.")
            form_fisica.addRow("Resistência dos cabos (Ω):", self.input_r_cabos)
        else:
            self.input_noise = QLineEdit("0.05")
            form_fisica.addRow("Fator de Ruído (0 a 1):", self.input_noise)

        grupo_fisica.setLayout(form_fisica)
        layout.addWidget(grupo_fisica)

        # --- Varredura ---
        titulo = ("Varredura SCPI" if self.modo == "bancada"
                  else "Varredura (Simulação)")
        grupo_varredura = QGroupBox(titulo)
        form_varredura = QFormLayout()

        self.input_v_start = QLineEdit()
        self.input_v_end = QLineEdit()
        self.input_v_step = QLineEdit()
        self.input_delay = QLineEdit()
        self.input_t_minima = QLineEdit(str(TEMPERATURA_MINIMA_PADRAO))
        self.input_t_minima.setToolTip(
            "Só entram na regressão os pontos acima desta temperatura.\n"
            "Não afeta a coleta: tudo continua sendo medido e gravado.")

        rotulo_espera = ("Estabilização Térmica (ms):" if self.modo == "bancada"
                         else "Intervalo de Captura (ms):")
        form_varredura.addRow("Tensão Inicial (V):", self.input_v_start)
        form_varredura.addRow("Tensão Final (V):", self.input_v_end)
        form_varredura.addRow("Passo de Tensão (V):", self.input_v_step)
        form_varredura.addRow(rotulo_espera, self.input_delay)

        if self.modo == "bancada":
            self.input_n_leituras = QLineEdit("1")
            self.input_n_leituras.setToolTip(
                "Leituras da fotocorrente por ponto. Com N > 1 o software\n"
                "calcula a incerteza Tipo A (s/√N). Custa N vezes mais tempo.")
            form_varredura.addRow("Leituras por ponto (N):", self.input_n_leituras)

        form_varredura.addRow("Temp. mínima p/ regressão (K):", self.input_t_minima)
        grupo_varredura.setLayout(form_varredura)
        layout.addWidget(grupo_varredura)
        layout.addStretch()

    # -- perfis --------------------------------------------------------------

    def _recarregar_perfis(self):
        for combo, tipo in ((self.combo_led, "leds"),
                            (self.combo_filamento, "filamentos"),
                            (self.combo_varredura, "varreduras")):
            combo.blockSignals(True)
            combo.clear()
            for perfil in carregar_perfis(tipo):
                combo.addItem(perfil.rotulo, perfil)
            combo.blockSignals(False)

        # Para a simulação, começar pelo preset de varredura próprio dela.
        if self.modo == "simulacao":
            for i in range(self.combo_varredura.count()):
                if "Simula" in self.combo_varredura.itemData(i).nome:
                    self.combo_varredura.setCurrentIndex(i)
                    break

        self._aplicar_led()
        self._aplicar_filamento()
        self._aplicar_varredura()

        problemas = avisos()
        self.lbl_avisos.setText(
            "⚠ " + " | ".join(problemas) if problemas else "")

    def _aplicar_led(self):
        perfil = self.combo_led.currentData()
        if perfil is None:
            return
        self.input_lambda.setText(f"{perfil.lambda_nm:g}")
        self.input_delta_lambda.setText(f"{perfil.delta_lambda_nm:g}")
        self.combo_led.setToolTip(f"Fonte: {perfil.fonte}\n\n{perfil.observacao}")
        self.parametros_alterados.emit()

    def _aplicar_filamento(self):
        perfil = self.combo_filamento.currentData()
        if perfil is None:
            return
        self.input_alpha.setText(f"{perfil.alpha:g}")
        self.input_beta.setText(f"{perfil.beta:g}")
        self.combo_filamento.setToolTip(f"Fonte: {perfil.fonte}\n\n{perfil.observacao}")
        self.parametros_alterados.emit()

    def _aplicar_varredura(self):
        perfil = self.combo_varredura.currentData()
        if perfil is None:
            return
        self.input_v_start.setText(f"{perfil.v_start:g}")
        self.input_v_end.setText(f"{perfil.v_end:g}")
        self.input_v_step.setText(f"{perfil.v_step:g}")
        self.input_delay.setText(f"{perfil.delay_ms:g}")
        self.input_t_minima.setText(f"{perfil.t_minima:g}")
        if hasattr(self, "input_n_leituras"):
            self.input_n_leituras.setText(str(perfil.n_leituras))
        self.combo_varredura.setToolTip(perfil.observacao)
        self.parametros_alterados.emit()

    def _salvar_varredura(self):
        nome, confirmou = QInputDialog.getText(
            self, "Salvar perfil de varredura",
            "Nome do perfil (um nome existente será substituído):")
        if not confirmou or not nome.strip():
            return
        try:
            perfil = PerfilVarredura(
                nome=nome.strip(),
                v_start=float(self.input_v_start.text()),
                v_end=float(self.input_v_end.text()),
                v_step=float(self.input_v_step.text()),
                delay_ms=float(self.input_delay.text()),
                n_leituras=int(float(getattr(self, "input_n_leituras", None).text()))
                if hasattr(self, "input_n_leituras") else 1,
                t_minima=float(self.input_t_minima.text()),
                observacao="Salvo pelo operador.")
            caminho = acrescentar_perfil("varreduras", perfil)
        except (ValueError, OSError) as erro:
            QMessageBox.warning(self, "Não foi possível salvar", str(erro))
            return
        self._recarregar_perfis()
        for i in range(self.combo_varredura.count()):
            if self.combo_varredura.itemData(i).nome == perfil.nome:
                self.combo_varredura.setCurrentIndex(i)
                break
        QMessageBox.information(self, "Perfil salvo", f"Gravado em:\n{caminho}")

    # -- leitura -------------------------------------------------------------

    def _atualizar_r0(self):
        try:
            r0 = corrigir_r0_para_zero_celsius(
                float(self.input_r_frio.text()), float(self.input_t_ambiente.text()),
                float(self.input_alpha.text()), float(self.input_beta.text()))
        except (ValueError, ZeroDivisionError):
            self.lbl_r0.setText("R0 a 0 °C: —  (verifique os valores)")
            return
        self.lbl_r0.setText(f"→ R0 a 0 °C = {r0:.4f} Ω   (é este o valor usado no cálculo)")
        self.parametros_alterados.emit()

    def coletar(self) -> dict:
        """
        Lê os campos e devolve o dicionário de parâmetros do experimento.

        Levanta ValueError se algum campo estiver inválido — quem chama mostra
        a mensagem ao operador.
        """
        alpha = float(self.input_alpha.text())
        beta = float(self.input_beta.text())
        r_frio = float(self.input_r_frio.text())
        t_ambiente = float(self.input_t_ambiente.text())
        u_r_frio = float(self.input_u_r_frio.text())

        r0 = corrigir_r0_para_zero_celsius(r_frio, t_ambiente, alpha, beta)
        u_r0 = incerteza_r0_corrigido(r_frio, t_ambiente, alpha, beta,
                                      u_r_frio=u_r_frio,
                                      u_t_ambiente=INCERTEZA_TEMPERATURA_AMBIENTE)

        parametros = {
            'r0': r0, 'r_frio': r_frio, 't_ambiente': t_ambiente,
            'u_r_frio': u_r_frio, 'u_r0': u_r0,
            'alpha': alpha, 'beta': beta,
            'lam': float(self.input_lambda.text()),
            'delta_lam': float(self.input_delta_lambda.text()),
            'v_start': float(self.input_v_start.text()),
            'v_end': float(self.input_v_end.text()),
            'v_step': float(self.input_v_step.text()),
            'delay': float(self.input_delay.text()),
            't_minima': float(self.input_t_minima.text()),
            'perfil_led': self.combo_led.currentData().nome,
            'perfil_filamento': self.combo_filamento.currentData().nome,
            'perfil_varredura': self.combo_varredura.currentData().nome,
        }

        if self.modo == "bancada":
            parametros['r_cabos'] = float(self.input_r_cabos.text())
            parametros['n_leituras'] = int(float(self.input_n_leituras.text()))
        else:
            parametros['noise'] = float(self.input_noise.text())
            parametros['r_cabos'] = 0.0
            parametros['n_leituras'] = 1

        return parametros
