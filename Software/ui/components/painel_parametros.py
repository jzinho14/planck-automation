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
                               QHBoxLayout, QInputDialog, QMessageBox,
                               QStackedWidget)
from qfluentwidgets import SegmentedWidget
from PySide6.QtCore import Signal

from content.perfis import (carregar_perfis, acrescentar_perfil, salvar_perfis,
                            avisos, PerfilCompleto)
from core.hardware_manager import (preferencias, limite_corrente,
                                   CHAVE_LIMITE_CORRENTE)
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
        """
        Configuração organizada em SEÇÕES, não numa coluna única.

        A página tinha vinte campos empilhados e ficava ilegível. Agora cada
        assunto tem a sua seção, e o atalho de catálogo de cada assunto fica
        DENTRO dela, logo acima dos campos que preenche — em vez de num bloco
        separado, que obrigava a olhar em dois lugares para entender de onde
        veio um valor.
        """
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        layout.addWidget(self._grupo_perfil_completo())

        self.seletor_secao = SegmentedWidget()
        self.secoes = QStackedWidget()

        disponiveis = self._secoes_disponiveis()
        self._indice_secao = {}
        for chave, titulo, construtor in disponiveis:
            self._indice_secao[chave] = self.secoes.count()
            self.secoes.addWidget(construtor())
            self.seletor_secao.addItem(chave, titulo)

        # Ligado ao sinal, e não ao callback por item: o callback só dispara em
        # clique do usuário, então trocar de seção por código não funcionava.
        self.seletor_secao.currentItemChanged.connect(
            lambda chave: self.secoes.setCurrentIndex(
                self._indice_secao.get(chave, 0)))
        self.seletor_secao.setCurrentItem(disponiveis[0][0])

        layout.addWidget(self.seletor_secao)
        layout.addWidget(self.secoes)
        layout.addStretch()

    def _secoes_disponiveis(self) -> list:
        secoes = [
            ("filamento", "Filamento", self._secao_filamento),
            ("sensor", "Sensor (LED)", self._secao_sensor),
            ("varredura", "Varredura", self._secao_varredura),
        ]
        if self.modo in ("bancada", "completo"):
            secoes.append(("bancada", "Bancada", self._secao_bancada))
        if self.modo in ("simulacao", "completo"):
            secoes.append(("simulacao", "Simulação", self._secao_simulacao))
        return secoes

    def _grupo_perfil_completo(self) -> QGroupBox:
        """Perfil que guarda TODOS os campos — vale para todas as seções."""
        grupo = QGroupBox("Perfil de configuração")
        forma = QFormLayout()

        self.combo_completo = QComboBox()
        self.combo_completo.currentIndexChanged.connect(self._aplicar_completo)

        linha = QWidget()
        botoes = QHBoxLayout(linha)
        botoes.setContentsMargins(0, 0, 0, 0)
        self.btn_salvar = QPushButton("Salvar como…")
        self.btn_salvar.setToolTip(
            "Guarda TODOS os campos de TODAS as seções com um nome.\n"
            "Um nome existente é substituído.")
        self.btn_salvar.clicked.connect(self._salvar_completo)
        self.btn_excluir = QPushButton("Excluir")
        self.btn_excluir.clicked.connect(self._excluir_completo)
        botoes.addWidget(self.btn_salvar)
        botoes.addWidget(self.btn_excluir)
        botoes.addStretch()

        self.lbl_avisos = QLabel()
        self.lbl_avisos.setWordWrap(True)
        self.lbl_avisos.setStyleSheet("color: #ffb74d; font-size: 11px;")

        forma.addRow("Perfil ativo:", self.combo_completo)
        forma.addRow("", linha)
        forma.addRow("", QLabel("O software reabre no último perfil usado."))
        forma.addRow("", self.lbl_avisos)
        grupo.setLayout(forma)
        return grupo

    def _secao_filamento(self) -> QWidget:
        pagina = QWidget()
        forma = QFormLayout(pagina)

        self.combo_filamento = QComboBox()
        self.combo_filamento.currentIndexChanged.connect(self._aplicar_filamento)
        self.combo_filamento.setToolTip(
            "Preenche α e β. Você pode editar os valores à mão depois.")

        self.input_r_frio = QLineEdit("1.2")
        self.input_u_r_frio = QLineEdit("0.01")
        self.input_t_ambiente = QLineEdit(str(TEMPERATURA_AMBIENTE_PADRAO))
        self.input_alpha = QLineEdit()
        self.input_beta = QLineEdit()

        self.input_r_frio.setToolTip(
            "Resistência do filamento medida frio, na temperatura ambiente.\n"
            "Não é R0: o software converte para 0 °C automaticamente.")
        self.input_u_r_frio.setToolTip("Incerteza da medida acima.")
        self.input_t_ambiente.setToolTip(
            "Temperatura em que a resistência a frio foi medida.\n"
            "Errar aqui desloca TODAS as temperaturas calculadas.")

        self.lbl_r0 = QLabel()
        self.lbl_r0.setStyleSheet("color: #64B5F6; font-size: 11px;")
        for campo in (self.input_r_frio, self.input_u_r_frio,
                      self.input_t_ambiente, self.input_alpha, self.input_beta):
            campo.textChanged.connect(self._atualizar_r0)

        forma.addRow("Catálogo de coeficientes:", self.combo_filamento)
        forma.addRow("Resistência a frio medida (Ω):", self.input_r_frio)
        forma.addRow("Incerteza de R a frio (Ω):", self.input_u_r_frio)
        forma.addRow("Temperatura ambiente (°C):", self.input_t_ambiente)
        forma.addRow("", self.lbl_r0)
        forma.addRow("Coef. Linear α (K⁻¹):", self.input_alpha)
        forma.addRow("Coef. Quadrático β (K⁻²):", self.input_beta)
        return pagina

    def _secao_sensor(self) -> QWidget:
        pagina = QWidget()
        forma = QFormLayout(pagina)

        self.combo_led = QComboBox()
        self.combo_led.currentIndexChanged.connect(self._aplicar_led)
        self.combo_led.setToolTip(
            "Preenche λ e Δλ. Você pode editar os valores à mão depois.")

        self.input_lambda = QLineEdit()
        self.input_delta_lambda = QLineEdit()
        self.input_delta_lambda.setToolTip(
            "Meia largura espectral do LED. É quase sempre a MAIOR fonte\n"
            "de incerteza em h.")

        forma.addRow("Catálogo de LEDs:", self.combo_led)
        forma.addRow("Comprimento de Onda λ (nm):", self.input_lambda)
        forma.addRow("Largura espectral Δλ (nm):", self.input_delta_lambda)
        return pagina

    def _secao_varredura(self) -> QWidget:
        pagina = QWidget()
        forma = QFormLayout(pagina)

        self.combo_varredura = QComboBox()
        self.combo_varredura.currentIndexChanged.connect(self._aplicar_varredura)
        self.combo_varredura.setToolTip(
            "Preenche a faixa e o passo. Tudo continua editável à mão.")

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

        forma.addRow("Catálogo de varreduras:", self.combo_varredura)
        forma.addRow("Tensão Inicial (V):", self.input_v_start)
        forma.addRow("Tensão Final (V):", self.input_v_end)
        forma.addRow("Passo de Tensão (V):", self.input_v_step)
        forma.addRow(rotulo_espera, self.input_delay)

        if self.modo in ("bancada", "completo"):
            self.input_n_leituras = QLineEdit("1")
            self.input_n_leituras.setToolTip(
                "Leituras da fotocorrente por ponto. Com N > 1 o software\n"
                "calcula a incerteza Tipo A (s/raiz(N)). Custa N vezes mais tempo.")
            forma.addRow("Leituras por ponto (N):", self.input_n_leituras)

        forma.addRow("Temp. mínima p/ regressão (K):", self.input_t_minima)
        return pagina

    def _secao_bancada(self) -> QWidget:
        """
        Parâmetros de hardware — incluindo o limite de corrente (B4).

        O limite mora aqui, e não na página de coleta: é configuração, e
        configuração tem um lugar só. A página de Bancada apenas exibe o valor
        em vigor, para o operador conferir antes de iniciar.
        """
        pagina = QWidget()
        forma = QFormLayout(pagina)

        self.input_limite = QLineEdit(f"{limite_corrente():g}")
        self.input_limite.setToolTip(
            "Limite de corrente da fonte — proteção do filamento.\n"
            "A lâmpada em uso opera até 24 W; a 12 V isso dá 2,0 A.\n"
            "O valor fica gravado nos metadados de cada coleta.")
        self.input_limite.editingFinished.connect(self._gravar_limite)

        self.input_r_cabos = QLineEdit("0.0")
        self.input_r_cabos.setToolTip(
            "Resistência dos cabos da medição a 2 fios, descontada de R.\n"
            "Meça curto-circuitando as pontas; deixe 0 se não souber.")

        forma.addRow("Limite de corrente da fonte (A):", self.input_limite)
        forma.addRow("", QLabel("Proteção do filamento: a fonte não entrega "
                                "mais que isto, entrando em modo corrente "
                                "constante."))
        forma.addRow("Resistência dos cabos (Ω):", self.input_r_cabos)
        return pagina

    def _secao_simulacao(self) -> QWidget:
        pagina = QWidget()
        forma = QFormLayout(pagina)
        self.input_noise = QLineEdit("0.05")
        self.input_noise.setToolTip(
            "Amplitude do ruído somado à fotocorrente simulada, como\n"
            "fração do sinal. Só afeta a página de Simulação.")
        forma.addRow("Fator de Ruído (0 a 1):", self.input_noise)
        forma.addRow("", QLabel("Só afeta a página de Simulação; a coleta real "
                                "não usa este valor."))
        return pagina

    def _gravar_limite(self):
        try:
            preferencias().setValue(CHAVE_LIMITE_CORRENTE,
                                    float(self.input_limite.text()))
        except ValueError:
            pass

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
        # B4: o limite de corrente e configuracao, entao viaja com os
        # demais parametros e acaba nos metadados da coleta.
        parametros['limite_corrente'] = (float(self.input_limite.text())
                                         if hasattr(self, "input_limite")
                                         else limite_corrente())

        return parametros
