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

from content.perfis import (carregar_perfis, acrescentar_perfil, salvar_perfis,
                            avisos, PerfilCompleto)
from core.hardware_manager import preferencias
from utils.math_models import (corrigir_r0_para_zero_celsius,
                               TEMPERATURA_AMBIENTE_PADRAO,
                               TEMPERATURA_MINIMA_PADRAO)
from utils.error_models import incerteza_r0_corrigido, INCERTEZA_TEMPERATURA_AMBIENTE

# Nome do perfil completo em uso; o software reabre nele.
CHAVE_PERFIL_ATIVO = "Parametros/PerfilAtivo"


class PainelParametros(QWidget):
    """
    Campos de física e de varredura, alimentados por perfis.

    `modo` controla o que aparece:
      "bancada"   — inclui resistência de cabos e leituras por ponto
      "simulacao" — inclui fator de ruído, sem os campos de hardware
      "completo"  — inclui tudo; é o modo da página única de Parâmetros, onde
                    Simulação e Bancada bebem da MESMA fonte de configuração
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

        # --- Perfil completo: o estado inteiro da página ---
        grupo_completo = QGroupBox("Perfil")
        forma_completo = QFormLayout()

        self.combo_completo = QComboBox()
        self.combo_completo.currentIndexChanged.connect(self._aplicar_completo)

        linha_botoes = QWidget()
        botoes = QHBoxLayout(linha_botoes)
        botoes.setContentsMargins(0, 0, 0, 0)
        self.btn_salvar = QPushButton("💾 Salvar como…")
        self.btn_salvar.setToolTip(
            "Guarda TODOS os campos desta página com um nome.\n"
            "Um nome existente é substituído.")
        self.btn_salvar.clicked.connect(self._salvar_completo)
        self.btn_excluir = QPushButton("🗑 Excluir")
        self.btn_excluir.clicked.connect(self._excluir_completo)
        botoes.addWidget(self.btn_salvar)
        botoes.addWidget(self.btn_excluir)
        botoes.addStretch()

        forma_completo.addRow("Perfil ativo:", self.combo_completo)
        forma_completo.addRow("", linha_botoes)
        forma_completo.addRow("", QLabel(
            "Guarda todos os campos abaixo. O software reabre no último "
            "perfil usado."))

        self.lbl_avisos = QLabel()
        self.lbl_avisos.setWordWrap(True)
        self.lbl_avisos.setStyleSheet("color: #ffb74d; font-size: 11px;")
        forma_completo.addRow("", self.lbl_avisos)

        grupo_completo.setLayout(forma_completo)
        layout.addWidget(grupo_completo)

        # --- Atalhos de catálogo: preenchem parte dos campos ---
        grupo_perfis = QGroupBox("Atalhos de catálogo (opcionais)")
        form_perfis = QFormLayout()

        self.combo_led = QComboBox()
        self.combo_filamento = QComboBox()
        self.combo_varredura = QComboBox()
        self.combo_led.currentIndexChanged.connect(self._aplicar_led)
        self.combo_filamento.currentIndexChanged.connect(self._aplicar_filamento)
        self.combo_varredura.currentIndexChanged.connect(self._aplicar_varredura)

        for combo in (self.combo_led, self.combo_filamento, self.combo_varredura):
            combo.setToolTip("Preenche alguns campos. Você pode editar "
                             "qualquer valor à mão depois.")

        form_perfis.addRow("LED (sensor):", self.combo_led)
        form_perfis.addRow("Filamento:", self.combo_filamento)
        form_perfis.addRow("Varredura:", self.combo_varredura)
        form_perfis.addRow("", QLabel(
            "São só pontos de partida — todo campo continua editável à mão."))

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

        if self.modo in ("bancada", "completo"):
            self.input_r_cabos = QLineEdit("0.0")
            self.input_r_cabos.setToolTip(
                "Resistência dos cabos da medição a 2 fios, descontada de R.\n"
                "Meça curto-circuitando as pontas; deixe 0 se não souber.")
            form_fisica.addRow("Resistência dos cabos (Ω):", self.input_r_cabos)
        if self.modo in ("simulacao", "completo"):
            self.input_noise = QLineEdit("0.05")
            self.input_noise.setToolTip(
                "Amplitude do ruído somado à fotocorrente simulada, como\n"
                "fração do sinal. Só afeta a página de Simulação.")
            form_fisica.addRow("Fator de Ruído — simulação (0 a 1):", self.input_noise)

        grupo_fisica.setLayout(form_fisica)
        layout.addWidget(grupo_fisica)

        # --- Varredura ---
        titulo = ("Varredura (Simulação)" if self.modo == "simulacao"
                  else "Varredura")
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

        rotulo_espera = ("Intervalo de Captura (ms):" if self.modo == "simulacao"
                         else "Estabilização Térmica (ms):")
        form_varredura.addRow("Tensão Inicial (V):", self.input_v_start)
        form_varredura.addRow("Tensão Final (V):", self.input_v_end)
        form_varredura.addRow("Passo de Tensão (V):", self.input_v_step)
        form_varredura.addRow(rotulo_espera, self.input_delay)

        if self.modo in ("bancada", "completo"):
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

    def _recarregar_perfis(self, selecionar: str = None):
        """
        Repovoa as caixas de perfil.

        A ordem importa: os atalhos de catálogo são aplicados PRIMEIRO (eles
        preenchem parte dos campos), e o perfil completo por ÚLTIMO, para que
        o que o operador salvou prevaleça sobre os presets.
        """
        for combo, tipo in ((self.combo_led, "leds"),
                            (self.combo_filamento, "filamentos"),
                            (self.combo_varredura, "varreduras")):
            combo.blockSignals(True)
            combo.clear()
            for perfil in carregar_perfis(tipo):
                combo.addItem(perfil.rotulo, perfil)
            combo.blockSignals(False)

        self._aplicar_led()
        self._aplicar_filamento()
        self._aplicar_varredura()

        # Perfil completo: o último usado, salvo em QSettings.
        alvo = selecionar or preferencias().value(CHAVE_PERFIL_ATIVO, "")
        self.combo_completo.blockSignals(True)
        self.combo_completo.clear()
        completos = carregar_perfis("completos")
        for perfil in completos:
            self.combo_completo.addItem(perfil.rotulo, perfil)
        indice = next((i for i, p in enumerate(completos) if p.nome == alvo), 0)
        self.combo_completo.setCurrentIndex(indice)
        self.combo_completo.blockSignals(False)
        self._aplicar_completo()

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

    # -- perfil completo -----------------------------------------------------

    def _campos_do_perfil(self, perfil) -> None:
        """Escreve nos campos os valores de um PerfilCompleto."""
        pares = [
            (self.input_r_frio, perfil.r_frio), (self.input_u_r_frio, perfil.u_r_frio),
            (self.input_t_ambiente, perfil.t_ambiente),
            (self.input_alpha, perfil.alpha), (self.input_beta, perfil.beta),
            (self.input_lambda, perfil.lambda_nm),
            (self.input_delta_lambda, perfil.delta_lambda_nm),
            (self.input_v_start, perfil.v_start), (self.input_v_end, perfil.v_end),
            (self.input_v_step, perfil.v_step), (self.input_delay, perfil.delay_ms),
            (self.input_t_minima, perfil.t_minima),
        ]
        if hasattr(self, "input_r_cabos"):
            pares.append((self.input_r_cabos, perfil.r_cabos))
        if hasattr(self, "input_noise"):
            pares.append((self.input_noise, perfil.ruido))
        if hasattr(self, "input_n_leituras"):
            pares.append((self.input_n_leituras, perfil.n_leituras))

        for campo, valor in pares:
            campo.setText(f"{valor:g}")

    def _perfil_dos_campos(self, nome: str) -> PerfilCompleto:
        """Monta um PerfilCompleto com o que está na tela."""
        def numero(campo, padrao=0.0):
            try:
                return float(campo.text())
            except (ValueError, AttributeError):
                return padrao

        return PerfilCompleto(
            nome=nome,
            r_frio=numero(self.input_r_frio, 1.2),
            u_r_frio=numero(self.input_u_r_frio, 0.01),
            t_ambiente=numero(self.input_t_ambiente, 25.0),
            alpha=numero(self.input_alpha, 5.23e-3),
            beta=numero(self.input_beta, 7.0e-7),
            lambda_nm=numero(self.input_lambda, 590.0),
            delta_lambda_nm=numero(self.input_delta_lambda, 30.0),
            r_cabos=numero(getattr(self, "input_r_cabos", None), 0.0),
            ruido=numero(getattr(self, "input_noise", None), 0.05),
            v_start=numero(self.input_v_start, 1.0),
            v_end=numero(self.input_v_end, 10.0),
            v_step=numero(self.input_v_step, 0.5),
            delay_ms=numero(self.input_delay, 3000.0),
            n_leituras=int(numero(getattr(self, "input_n_leituras", None), 1)),
            t_minima=numero(self.input_t_minima, 1800.0),
            observacao="Salvo pelo operador.")

    def _aplicar_completo(self):
        perfil = self.combo_completo.currentData()
        if perfil is None:
            return
        self._campos_do_perfil(perfil)
        self.combo_completo.setToolTip(perfil.observacao)
        preferencias().setValue(CHAVE_PERFIL_ATIVO, perfil.nome)
        self._atualizar_r0()
        self.parametros_alterados.emit()

    def _salvar_completo(self):
        atual = self.combo_completo.currentText().split("  (")[0]
        nome, confirmou = QInputDialog.getText(
            self, "Salvar perfil",
            "Nome (um nome existente será substituído):", text=atual)
        if not confirmou or not nome.strip():
            return
        try:
            perfil = self._perfil_dos_campos(nome.strip())
            caminho = acrescentar_perfil("completos", perfil)
        except (ValueError, OSError) as erro:
            QMessageBox.warning(self, "Não foi possível salvar", str(erro))
            return

        self._recarregar_perfis(selecionar=perfil.nome)
        QMessageBox.information(
            self, "Perfil salvo",
            f"'{perfil.nome}' guardado com TODOS os campos desta página.\n\n{caminho}")

    def _excluir_completo(self):
        perfil = self.combo_completo.currentData()
        if perfil is None:
            return
        if self.combo_completo.count() <= 1:
            QMessageBox.warning(self, "Não é possível excluir",
                                "É o único perfil; crie outro antes de apagar este.")
            return
        resposta = QMessageBox.question(
            self, "Excluir perfil", f"Apagar o perfil '{perfil.nome}'?")
        if resposta != QMessageBox.Yes:
            return
        restantes = [p for p in carregar_perfis("completos") if p.nome != perfil.nome]
        salvar_perfis("completos", restantes)
        self._recarregar_perfis()

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

        # Cada campo ausente ganha um padrão inerte, para que qualquer página
        # possa consumir o mesmo dicionário sem precisar saber do modo.
        parametros['r_cabos'] = (float(self.input_r_cabos.text())
                                 if hasattr(self, "input_r_cabos") else 0.0)
        parametros['n_leituras'] = (int(float(self.input_n_leituras.text()))
                                    if hasattr(self, "input_n_leituras") else 1)
        parametros['noise'] = (float(self.input_noise.text())
                               if hasattr(self, "input_noise") else 0.05)

        return parametros
