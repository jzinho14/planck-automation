# CLAUDE.md — Planck Automation (Constante de Planck via Radiação de Corpo Negro)

> Este arquivo orienta o Claude Code ao trabalhar neste repositório.
> Foi gerado a partir de uma análise completa do código, do artigo de referência
> (Cavalcante & Haag, RBEF v.27 n.3, 2005, em `Docs/`) e dos datasheets dos
> instrumentos Tektronix (DMM4050 e PWS4323, em `Docs/`).

---

## 1. Contexto do projeto

Software de bancada (PySide6 + PyVISA + pyqtgraph) para determinar a constante de
Planck **h** medindo a radiação de um filamento de tungstênio (aproximado como corpo
negro/cinza) com LEDs usados como sensores espectrais seletivos.

**Física (aproximação de Wien):**
- `I(λ,T) ≈ (2πc²h/λ⁵)·exp(−hc/(λ·k_B·T))`
- Linearização: `ln(I_led) × 1/T` → reta de inclinação `m = −hc/(λ·k_B)`
- Portanto: `h = −m·λ·k_B/c`
- Temperatura do filamento via resistência: `R(Tc) = R0·(1 + a·Tc + b·Tc²)`, Tc em °C,
  resolvida por Bhaskara (Eq. 12 do artigo).

**Hardware:**
- **Fonte Tektronix PWS4323** (0–32 V, 0–3 A): aquece o filamento. Conexão USB (VISA).
- **Multímetro Tektronix DMM4050** (6½ dígitos): lê a fotocorrente do LED (faixa fixa
  de 100 µA, resolução até 100 pA). Conexão TCP/IP SOCKET (`TCPIP::<ip>::3490::SOCKET`).
- Protocolo SCPI via PyVISA (`ResourceManager('@ivi')` — backend NI-VISA no Windows).

**Fluxo de um experimento:** varredura de tensão (v_start → v_end, passo v_step),
espera de estabilização térmica por ponto, leitura de I_filamento (fonte) e I_led (DMM),
cálculo de R = V/I → T, gravação incremental em `data_backup/*.csv`, regressão linear
ao final → h, erro relativo e R².

> **Pendências humanas ficam em `PENDENCIAS.txt`** (raiz). São itens que
> precisam de decisão ou verificação do usuário — nenhum deles bloqueia o
> desenvolvimento. Ao deixar algo em aberto de propósito, registre lá em vez de
> travar a fase.

## 2. Regras para o Claude Code

1. **O software funciona na bancada real.** Nunca quebrar o fluxo de coleta existente.
   Refatore em passos pequenos e testáveis; preserve o formato dos CSVs já gerados
   (há dados históricos em `Software/data_backup/`).
2. **Modularidade é prioridade do usuário.** Ele quer escolher os parâmetros que está
   usando (LED, filamento, instrumento, varredura) de forma plugável — ver §8.
3. Idioma da UI e dos comentários: **português (pt-BR)**.
4. Sem hardware no computador de desenvolvimento: qualquer trabalho na lógica de
   coleta deve vir acompanhado de um **modo mock/simulado dos drivers** (ver §9, Fase 1)
   para poder testar sem a bancada.
5. Segurança da bancada é inegociável: em qualquer caminho de erro/parada, a fonte
   deve ser zerada e desligada (`turn_off_safely`). Não remover esses guards.
6. Rodar: `cd Software && python main.py` (venv em `Software/.venv`).
   Dependências: `Software/requirements.txt`.
7. **Documentação LaTeX:** editar os `.tex` à vontade, mas **não compilar a cada
   edição** — compilar só no fim do trabalho, uma vez, antes de commitar.
8. **Teoria explícita.** O usuário vai apresentar a fundamentação ao orientador.
   Toda escolha de modelagem (especialmente de incerteza) deve estar visível e
   justificada no código e em `Documentacao/manual_tecnico.tex`, com as
   equações numeradas — não basta funcionar, tem que ser auditável.

## 3. Arquitetura atual (mapa real do código)

```
Software/
├── main.py                      # QApplication + Fusion + tema QSS escuro
├── content/
│   ├── referencias.py           # dataclass Referencia + lista REFERENCIAS (dado, não código)
│   └── perfis.py                # 4 famílias de perfis + carga tolerante a falha
├── profiles/                    # leds.json, filamentos.json, instrumentos.json,
│                                #   varreduras.json — editáveis sem tocar em código
├── core/
│   ├── hardware_manager.py      # Drivers SCPI (PWS4323, DMM4050), ScannerThread,
│   │                            #   ValidatorThread, HardwareManager(QObject),
│   │                            #   obter_drivers()/modo_demonstracao_ativo()
│   ├── mock_hardware.py         # BancadaSimulada + Mock*_Driver (mesma interface)
│   └── metadados.py             # JSON irmão de cada CSV (P5 — rastreabilidade)
├── ui/
│   ├── main_window.py           # QTabWidget com 4 abas
│   ├── theme.py                 # DARK_THEME (string QSS)
│   ├── components/
│   │   ├── connection_panel.py  # Scan/validação VISA, persiste em QSettings("Senac","PlanckAutomation")
│   │   ├── painel_parametros.py # ← COMPARTILHADO pelas duas abas (fim da duplicação)
│   │   └── export_dialog.py     # Metadados do relatório PDF
│   └── tabs/
│       ├── tab_simulation.py    # SimulationWorker(QThread) + UI de simulação
│       ├── tab_experiment.py    # ExperimentWorker(QThread) + UI da bancada real
│       └── tab_references.py    # renderiza content/referencias.py (artigo + manuais)
├── utils/
│   ├── math_models.py           # corrigir_r0_para_zero_celsius, calculate_temperature,
│   │                            #   selecionar_pontos_validos, simulate_experiment_data,
│   │                            #   calculate_planck_constant
│   ├── error_models.py          # GUM: Tipo A/B, propagação, ajuste ponderado,
│   │                            #   analisar_experimento() → h ± U + orçamento
│   └── pdf_exporter.py          # Relatório PDF via reportlab
└── data_backup/                 # exp_planck_*.csv (bancada real) e demo_planck_*.csv
                                 #   (simulados). Colunas: Tensao_Fonte_V,
                                 #   Corrente_Filamento_A, Resistencia_Ohms, Temperatura_K,
                                 #   Fotocorrente_A, Tensao_Medida_V (nova, ao final)
Tests/test_connection.py         # Scan VISA standalone (espelha o ScannerThread)
Tests/test_mock_hardware.py      # 17 checagens da bancada simulada (roda sem hardware)
Tests/test_math_models.py        # 25 checagens do modelo fisico (A2, A5, regressao)
Tests/test_error_models.py       # 40 checagens da teoria de erros (Tipo A/B, ajuste, propagacao)
Tests/test_perfis_metadados.py   # 40 checagens de perfis e metadados por coleta
Tests/test_interface.py          # ponta a ponta pela UI real, sem hardware
Tests/calibrar_mock_com_dados_reais.py  # procedencia das constantes do mock (nao e teste)
Markdowns/project_description.md # Especificação original (as abas Análise e Comparação ainda faltam)
Docs/                            # Artigo de referência + datasheets Tektronix
```

**Acoplamentos importantes:**
- `tab_experiment.start_experiment()` lê as strings VISA de `QSettings` gravadas pelo
  `ConnectionPanel` (acoplamento por side-channel, não por sinal — candidato a refatoração).
- `ExperimentWorker` instancia os drivers direto na thread (correto para VISA), mas os
  parâmetros de segurança (limite de corrente 2.0 A) estão hardcoded.
- A especificação original previa Aba de "Reconstrução/Comparação" e Aba de
  "Processamento Analítico passo a passo" — **nunca foram implementadas**.

## 4. Verificação da teoria contra o artigo (achados)

Conferi `utils/math_models.py` e os workers contra Cavalcante & Haag (2005). A física
central está correta; há 4 problemas de exatidão que afetam o resultado:

- **A1 — Fórmula de h: CORRETA.** `h = −m·λ·k_B/c` reproduz a Eq. 13 do artigo
  (inclinação = hc/λk_B). Bhaskara em `calculate_temperature` reproduz a Eq. 12
  (raiz física positiva, +273.15). ✔
- **A2 — Semântica de R0: INCORRETA (erro sistemático).** No artigo, `R0` é a
  resistência a **0 °C** (Eq. 10). O software pede "Resistência a Frio R0 (Ω)" — que o
  operador mede à temperatura **ambiente** — e usa esse valor diretamente como R0.
  Falta a correção da Eq. 11: `R0 = R(T_amb)/(1 + a·T_amb + b·T_amb²)`.
  A ~25 °C isso desloca R0 em ~13% e enviesa todas as temperaturas (e portanto h).
  **Correção:** adicionar campo "Temperatura ambiente (°C)" e aplicar a Eq. 11
  automaticamente (ou um botão "Medir R0 agora" que injeta corrente baixa via fonte).
- **A3 — Coeficientes do tungstênio divergem do artigo.** Código usa por padrão
  α=5.23e-3, β=7.0e-7; o artigo (fonte PHYWE) usa a=4.82e-3 K⁻¹, b=6.76e-7 K⁻².
  Se os valores do código vêm de outra referência, documentar; senão, adotar os do
  artigo. Ideal: presets de filamento com fonte citada (ver §8).
- **A4 — R do filamento usa a tensão programada, não a medida.** `r_fil = v_target/i_fil`
  usa o setpoint da fonte. A PWS4323 tem *readback* de tensão com exatidão
  ±(0,02% + 3 mV) — melhor que a exatidão de *setting* ±(0,05% + 10 mV). Usar
  `MEAS:VOLT?` da fonte. Além disso a medição é 2 fios: a resistência dos cabos
  entra em R. Oferecer campo "R dos cabos (Ω)" para subtração (ou remote sense).
- **A5 — Temperaturas não físicas em baixa tensão.** Os CSVs reais mostram T≈77 K
  em V≈0 (matematicamente correto pela Bhaskara, fisicamente absurdo — resistência
  medida menor que R0). Não há guard para discriminante negativo (→ NaN) nem para
  T < T_ambiente. A regressão deve usar só a região de Wien/alta temperatura
  (ex.: T > 1000 K) e a UI deve sinalizar pontos descartados.
- **A6 — Validade de Wien: OK, documentar.** x = hc/(λ·k_B·T) ≈ 24387/T·(590nm/λ).
  Pior caso (λ=590 nm, T=3000 K): x≈8.1 → erro de trocar Planck por Wien ≈ e^−x ≈ 0,03%.
  Desprezível frente aos demais erros. Vale exibir esse check na UI de análise.
- **A7 — Largura espectral do LED domina o erro de λ.** O artigo usa Δλ = ±25–35 nm
  (limita a precisão a ~7,6% no pior caso). O software hoje trata λ como exato.
  σ_λ deve entrar na propagação de erros (ver §6) e o cadastro de LEDs deve ter λ ± Δλ.
- **A8 — Fotodetecção direta no DMM: OK.** O artigo usa amplificador de
  transimpedância; aqui o LED alimenta direto a entrada de corrente do DMM4050.
  Na faixa de 100 µA a *burden voltage* é < 0,015 V — quase curto-circuito, regime
  linear do LED como fotodetector. Justificado; documentar no help da UI.
- **A9 — Simulação fisicamente inconsistente.** `simulate_experiment_data` impõe
  T = linspace(1500, 3000) **independente das tensões** — a simulação não reproduz a
  relação V→T do experimento (balanço de energia, Eq. 9 do artigo: V·i = C·ΔT + ε·σ·A·(T⁴−T0⁴)).
  Melhorar para resolver T(V) pelo balanço de energia ou por R(V) empírico.
- **A10 — Oportunidade: lei de Stefan-Boltzmann.** O artigo verifica também
  log(V·i) × log(T) → inclinação ≈ 4. Os CSVs já contêm todas as colunas
  necessárias. É um módulo de análise barato de adicionar e de alto valor didático.

## 5. Bugs conhecidos (confirmados por leitura, não corrigir sem testar)

- **B1 — `ui/main_window.py`: abas duplicadas.** O bloco `addTab` das 3 abas aparece
  **duas vezes** em `setup_ui()` — a janela mostra 6 abas (3 repetidas, apontando
  para os mesmos widgets). Remover o segundo bloco.
- **B2 — `core/hardware_manager.py`: `DMM4050_Driver` tem `read_current` e `close`
  definidos DUAS vezes.** Em Python a segunda definição vence: o `close()` efetivo
  **não envia `SYST:LOC`** (o multímetro fica travado em modo remoto ao final).
  Apagar as duplicatas mantendo a versão com `SYST:LOC`.
- **B3 — `utils/math_models.py`: código morto.** Em `calculate_planck_constant` há um
  `return` seguido de docstring + uma segunda implementação inteira, inalcançável.
  Limpar (mantendo a versão ativa, que tem o filtro `limiar_confianca`).
- **B4 — Limite de segurança inconsistente.** `configure_safety_limits(max_current=2.0)`
  com comentário dizendo 1.5 A. Tornar parâmetro configurável na UI com default seguro.
- **B5 — IP do DMM hardcoded** (`192.168.1.107:3490`) em `ScannerThread` e em
  `Tests/test_connection.py`. Mover para configuração editável na UI/QSettings.
- **B6 — Threshold de regressão abaixo do piso do instrumento.** `limiar_confianca = 1e-9`
  (1 nA), mas a exatidão do DMM na faixa 100 µA tem termo de fundo de 25 nA (ver §6).
  O threshold deve derivar do modelo de erro instrumental, não ser mágico.
- **B7 — Progress bar pode divergir do nº real de pontos** (`int((v_end−v_start)/v_step)+1`
  vs `len(np.arange(v_start, v_end+v_step, v_step))` — aritmética de float). Usar o
  mesmo vetor de tensões para ambos.
- **B8 — `ValidatorThread`s acumulam** em `self._validators` sem limpeza (leak leve).
- **B9 — Divisão por zero possível em R²** (`ss_tot == 0`) e em `1/T` se T=0. Guards.
- **B10 — Arquivos vazios** (`data_logger.py`, `experiment_runner.py`, `plot_widget.py`,
  `README.md`): implementar ou remover — hoje só confundem. O JSON de metadados por
  experimento prometido na especificação nunca foi implementado.

## 6. Teoria de erros — guia e plano de implementação (prioridade do usuário)

### 6.1 Conceitos (nomenclatura GUM, que o software deve adotar)

- **Erro Tipo A (estatístico):** estimado por repetição. Para cada ponto da varredura,
  fazer N leituras (N configurável, ex. 5–10) → média e desvio padrão da média
  `σ_A = s/√N`.
- **Erro Tipo B (instrumental):** vem do datasheet. Especificação típica
  `±(% da leitura + % da faixa)` define um limite `a` de distribuição retangular;
  a incerteza padrão é `u_B = a/√3`.
- **Combinação:** `u = √(u_A² + u_B²)` por ponto medido.
- **Propagação:** para `f(x, y, ...)`, `u_f² = (∂f/∂x)²u_x² + (∂f/∂y)²u_y² + ...`
  (variáveis independentes).
- **Resultado final:** reportar `h = (valor ± U) J·s` com incerteza expandida
  `U = k·u_c`, k=2 (~95%), e algarismos significativos coerentes (incerteza com
  1–2 algarismos; valor arredondado na mesma casa).

### 6.2 Especificações instrumentais extraídas dos datasheets (usar estes números)

**DMM4050 — corrente DC, faixa 100 µA (a usada para o LED), spec 1 ano, 23±5 °C:**
- Exatidão: **±(0,05% da leitura + 0,025% da faixa)** → termo de faixa = **25 nA**.
- Resolução (6½ díg.): 100 pA. NPLC 10 (config. atual): sem erro adicional de ruído.
- Consequência crítica: fotocorrentes de poucos nA (comuns nos CSVs reais em baixa T)
  têm incerteza instrumental dominada pelos 25 nA de fundo → esses pontos quase não
  carregam informação. **É exatamente por isso que a regressão precisa ser ponderada.**

**PWS4323 (fonte), 25±5 °C:**
- *Readback* de tensão: **±(0,02% da leitura + 3 mV)** ← usar para V do filamento.
- *Setting* de tensão (sem remote sense): ±(0,05% + 10 mV) ← é o que o código usa hoje.
- *Readback* de corrente: **±(0,05% da leitura + 2 mA)** ← domina o erro de R em
  correntes baixas; para R0 a frio considerar medir corrente com o DMM se necessário.

**LED (dominante em h):** λ ± Δλ com Δλ ≈ 25–35 nm (meia largura espectral, artigo §3.3).
Tratar como retangular: `u_λ = Δλ/√3` (documentar a escolha).

### 6.3 Cadeia de propagação a implementar (novo módulo `utils/error_models.py`)

```
u(V)  = f(readback PWS)          u(I_fil) = f(readback PWS)
   └── R = V/I_fil:  (u_R/R)² = (u_V/V)² + (u_I/I)²
          └── T = Bhaskara(R, R0, a, b):  u_T = |dT/dR|·u_R  ⊕  termos de u_R0, u_a, u_b
                 dT/dR = 1 / (R0·(a + 2b·Tc))          [derivada analítica, Tc em °C]
u(I_led) = 0,0005·I_led + 25e-9  (DMM, faixa 100µA)  → u_y = u(I_led)/I_led   [y = ln I]
u_x = u_T / T²                                        [x = 1/T]
   └── Regressão LINEAR PONDERADA (WLS) com u_y  →  m ± u_m, c ± u_c, R², χ²_red
       (ideal: scipy.odr, que aceita erro em x E em y — u_x não é desprezível)
          └── h = −m·λ·k_B/c_luz:
              (u_h/h)² = (u_m/m)² + (u_λ/λ)²     ← u_λ costuma dominar (~3–5%)
```

Implementação sugerida:
- `utils/error_models.py`: dataclasses `InstrumentSpec` (pct_leitura, termo_fixo,
  distribuição) e funções puras `u_dmm_current(i)`, `u_pws_voltage(v)`, `u_temperature(...)`,
  `weighted_linear_fit(x, y, u_x, u_y)` (WLS analítico e/ou `scipy.odr`).
- As specs dos instrumentos vivem em **perfis JSON** (§8), não hardcoded — se o usuário
  trocar de multímetro, só troca o perfil.
- Testes unitários com valores conhecidos (ex.: conferir u_m do WLS contra
  `numpy.polyfit(..., w=...)` e caso analítico simples).
- Adicionar `scipy` ao `requirements.txt`.
- **UI:** cada resultado passa a exibir `h = (6,61 ± 0,21)×10⁻³⁴ J·s (k=2)` + um
  painel/tabela **"Orçamento de incertezas"** (contribuição de cada fonte em % — muito
  didático e é o que o usuário quer aprender).

## 7. Interface — DECISÃO TOMADA: PySide6 + QFluentWidgets

O usuário escolheu migrar a UI para **QFluentWidgets** (pacote `PySide6-Fluent-Widgets`,
visual Fluent/Windows 11), mantendo PySide6, pyqtgraph e o fluxo de empacotamento
PyInstaller + Inno Setup que ele já usa.

Problemas da UI atual: abas dentro de abas (navegação confusa), status de hardware
invisível fora da 1ª aba, QLineEdit sem validação/unidade, parâmetros repetidos entre
Simulação e Experimento, resultados sem incerteza, duas abas da especificação faltando.

**Diretrizes de implementação com QFluentWidgets:**
- Janela principal: `FluentWindow` com `NavigationInterface` (sidebar) — cada página
  vira uma sub-interface registrada com `addSubInterface(widget, ícone, título)`.
- Componentes a usar: `CardWidget`/`HeaderCardWidget` para os painéis e resultados,
  `InfoBar` para notificações (sucesso/erro de conexão, fim de coleta),
  `PrimaryPushButton`/`PushButton`, `DoubleSpinBox`/`LineEdit` da própria lib,
  `ComboBox` para os perfis (§8), `SwitchButton` para modo demonstração/tema,
  `IndeterminateProgressRing`/`ProgressBar` na coleta, `setTheme(Theme.DARK)` +
  `setThemeColor` para identidade visual.
- pyqtgraph continua sendo o motor dos gráficos em tempo real (embutir o
  `GraphicsLayoutWidget` dentro de um `CardWidget`).
- **Atenção à licença:** PyQt/PySide6-Fluent-Widgets (versão comunitária) é **GPLv3**.
  Para um software de laboratório didático distribuído gratuitamente, ok — mas o
  projeto deve ser licenciado compativelmente (GPLv3) se for distribuído.
- Adicionar `PySide6-Fluent-Widgets` ao `requirements.txt`. Verificar compatibilidade
  de versão com o PySide6 fixado (a lib documenta as faixas suportadas).
- O `theme.py`/QSS atual deixa de ser necessário aos poucos; remover só ao final da
  migração (páginas antigas e novas podem coexistir durante a transição).

**Estrutura de navegação proposta:**

```
┌────────────────────────────────────────────────────────────────────┐
│ Header fixo: ● PWS4323 (conectada)  ● DMM4050 (conectado)  [Tema] │
├──────────┬─────────────────────────────────────────────────────────┤
│ Sidebar  │  Área central (páginas do FluentWindow)                 │
│ 🔌 Conexão   │   – painel da página selecionada, tela cheia        │
│ ⚙ Parâmetros │   – SEM sub-abas: config e execução na mesma tela   │
│ 💻 Simulação │     (parâmetros à esquerda em painel colapsável,    │
│ 🔬 Bancada   │      gráficos à direita)                            │
│ 📊 Análise   │                                                     │
│ 📄 Relatório │                                                     │
├──────────┴─────────────────────────────────────────────────────────┤
│ QStatusBar: "Salvando em data_backup/exp_... | ponto 14/23 | 2310 K"│
└────────────────────────────────────────────────────────────────────┘
```

Diretrizes por página:
- **Conexão:** o painel atual + campo editável de IP/porta do DMM (resolve B5) +
  limite de corrente da fonte (resolve B4).
- **Parâmetros (nova, central ao pedido de modularidade):** seleção de perfis (§8) —
  LED (λ ± Δλ), filamento (R0, a, b, com fonte), instrumentos (specs de erro),
  varredura. Um único lugar; Simulação e Bancada **consomem** os mesmos perfis
  (elimina a duplicação atual de campos). Entradas em `QDoubleSpinBox` com unidade,
  faixa válida e tooltip explicando a física do parâmetro.
- **Bancada:** LEDs semânticos de estado (🟢/🟡/🔴), botão de emergência sempre
  visível, gráficos ao vivo (manter pyqtgraph), log em fonte mono. Pontos abaixo do
  piso de 25 nA plotados em cinza (excluídos da regressão) — feedback visual do
  modelo de erro (A5/B6).
- **Análise (nova — cumpre as Abas 3 e 4 da especificação original):** carregar
  múltiplos CSVs (real × simulado), sobrepor curvas, recomputar h com regressão
  ponderada, pipeline passo a passo (1/T → ln I → WLS → h), tabela de orçamento de
  incertezas e check de Stefan-Boltzmann (inclinação log(V·i)×log(T) ≈ 4).
- **Relatório:** PDF atual + seção de incertezas + tabela de pontos usados/descartados.
- Manter tema escuro; mover QSS para arquivo `theme.qss`; opcional light mode.

## 8. Sistema modular de parâmetros (desejo explícito do usuário)

Criar `Software/profiles/` com JSONs versionáveis + dataclasses de carga:

```
profiles/
├── leds.json         # [{nome:"Vermelho 660nm", lambda_nm:660, delta_lambda_nm:35, fonte:"Mims 1992"}, ...]
├── filamentos.json   # [{nome:"Artigo RBEF/PHYWE", r0_ohm:null, a:4.82e-3, b:6.76e-7,
│                     #   fonte:"Cavalcante & Haag 2005, Eq.10"}, {nome:"Atual do software", a:5.23e-3, b:7.0e-7, ...}]
├── instrumentos.json # [{nome:"DMM4050 100µA 1yr", pct_leitura:0.0005, termo_fixo:25e-9, dist:"retangular"},
│                     #  {nome:"PWS4323 V readback", pct_leitura:0.0002, termo_fixo:3e-3, ...}]
└── varreduras.json   # presets de v_start/v_end/step/delay/n_leituras
```

- ComboBox de perfil em "Parâmetros" + botão "Personalizado" (salva novo perfil).
- R0 continua sendo medido por experimento (não é propriedade do perfil), com a
  correção A2 aplicada.
- Metadados do experimento (perfis usados, timestamps, resultados, incertezas) salvos
  em JSON ao lado do CSV — cumpre a promessa da especificação original e dá
  rastreabilidade aos relatórios.

## 9. Roadmap sugerido (uma fase por sessão de trabalho)

1. ~~**Fase 0 — Correções seguras**~~ ✅ **CONCLUÍDA.** B1, B2, B3, B7, B8, B9 e a
   limpeza de B10, um commit por bug. Também corrigido o `ScannerThread`, que tinha
   o mesmo problema de referência do B8. Restam abertos B4, B5 e B6.
2. ~~**Fase 1 — Testabilidade**~~ ✅ **CONCLUÍDA.** `core/mock_hardware.py` com
   `BancadaSimulada` + `MockPWS4323_Driver`/`MockDMM4050_Driver`, e a flag
   "Modo demonstração" na aba de Ligações (persistida em QSettings).
   - `k_rad`/`k_cond` do balanço de energia vieram de mínimos quadrados sobre os
     1127 pontos úteis dos CSVs reais (resíduo mediano de 2,9% em potência),
     reescalados para o filamento virtual bater 2540 K em 12 V.
   - O mock **reproduz de propósito** o piso de ~4,5 nA do DMM: numa varredura
     completa (0,5–12 V) o h sai ~76% errado, e restrito à região de Wien
     (6–12 V) sai a ~3%. É a reprodução fiel de A5/B6 — o alvo das Fases 2 e 3.
   - Coletas simuladas gravam `data_backup/demo_planck_*.csv`, separadas do
     acervo real `exp_planck_*.csv`.
3. ~~**Fase 2 — Correções de física**~~ ✅ **CONCLUÍDA.**
   - **A2** — `corrigir_r0_para_zero_celsius` (Eq. 11). A UI pede "resistência a
     frio medida" + "temperatura ambiente (°C)" e mostra ao vivo o R0 resultante.
     A 25 °C são ~13% de viés removidos.
   - **A3** — `content/filamentos.py` com dois presets **e a fonte de cada um**.
     O padrão continua sendo α=5.23e-3/β=7.0e-7 (procedência não documentada, mas
     é com ele que todo o `data_backup/` foi processado); o do artigo
     (4.82e-3/6.76e-7) está disponível na lista. **Trocar o padrão é decisão do
     usuário, não minha.**
   - **A4** — `PWS4323_Driver.measure_voltage()` (`MEAS:VOLT?`); o worker calcula
     `R = V_medida/i − R_cabos`, com campo de R_cabos na UI e fallback para o
     setpoint se o readback falhar. Nova coluna `Tensao_Medida_V` **ao final** do
     CSV, para não mexer na ordem das 5 históricas.
   - **A5** — `selecionar_pontos_validos()`: descarta T≤0/NaN, aplica corte de
     região de Wien (padrão 1800 K, configurável) e o limiar de corrente. Pontos
     descartados aparecem **em cinza** nos gráficos das duas abas, marcados no log
     e contados no status e no PDF.
   - **O corte é na regressão, não na varredura**: dá para varrer 0–12 V e ainda
     assim ter bom h. Medido: a mesma varredura completa vai de 99,0% de erro
     (sem corte) para 5,6% (corte em 1800 K), com R² de 0,062 → 0,997.
   - `Tests/test_math_models.py` (22 checagens) + o critério de aceitação do A5
     fixado em `Tests/test_mock_hardware.py`.
   - **Aberto:** A6, A7, A8 (documentação/incerteza — Fase 3), A9, A10.
4. ~~**Fase 3 — Teoria de erros**~~ ✅ **CONCLUÍDA (motor; painel visual na Fase 5).**
   - `utils/error_models.py`: specs de instrumento como dataclasses, Tipo A/B,
     propagação com derivadas analíticas, ajuste ponderado e orçamento.
   - **Ajuste:** WLS + método da **variância efetiva** (Orear 1982 / York 1968)
     em numpy puro. **Não usa `scipy.odr` — está deprecada e sai na 1.19.**
     Nenhuma dependência nova foi adicionada.
   - **B6 morto:** o limiar de corrente agora sai de
     `limiar_corrente_confiavel()` (≈25 nA, o termo de fundo do DMM4050) em vez
     do 1 nA arbitrário — que era menor que o próprio ruído e não filtrava nada.
   - **Aleatório × sistemático:** R0/α/β são comuns a toda a varredura e NÃO
     entram no peso dos pontos; são propagados por sensibilidade (refazendo o
     ajuste com o parâmetro deslocado). Pôr sistemático no peso derrubava o
     χ²_red de 0,101 para 0,035 e inflava u_m de 615 para 1099.
   - **Tipo A:** campo "Leituras por ponto (N)", padrão 1 (comportamento atual).
     Com N>1 grava desvio e nº de leituras no CSV.
   - UI mostra `h = (6,50 ± 0,52)×10⁻³⁴ J·s (k=2)`, χ²_red, orçamento resumido
     e veredicto de compatibilidade com a CODATA. PDF ganhou tabela de orçamento.
   - **Toda a teoria está no `manual_tecnico.tex` §"Teoria de erros"** e nas
     hipóteses H1–H6 do cabeçalho de `error_models.py` — para revisão do
     orientador (PENDENCIAS.txt, P2).
5. ~~**Fase 4 — Perfis modulares**~~ ✅ **CONCLUÍDA.**
   - `profiles/*.json` com quatro famílias (LEDs, filamentos, instrumentos,
     varreduras). Todo perfil de constante física carrega a sua **fonte**.
   - Carga **tolerante a falha**: JSON ausente, corrompido ou com campos
     faltando cai para os padrões embutidos e registra aviso na UI. Um
     laboratório não pode parar por causa de uma vírgula num JSON.
   - `ui/components/painel_parametros.py`: **um componente para as duas abas**
     (modo "bancada"/"simulacao"), no lugar dos campos duplicados. Sobrevive à
     migração da Fase 5 — só muda quem o hospeda.
   - Trocar de multímetro passa a ser editar `instrumentos.json`: as specs
     alimentam `error_models` direto.
   - **P5 resolvido:** `core/metadados.py` grava um JSON irmão de cada CSV,
     com perfis, R0 medido *e* corrigido, varredura, modo e o resultado com
     incerteza. Gravado na abertura E no encerramento.
   - Botão "salvar varredura atual como perfil" no painel.
6. **Fase 5 — Nova interface (§7):** migrar para `FluentWindow` + QFluentWidgets,
   uma página por vez (começar pela Conexão, que é a mais simples), mantendo as
   telas antigas funcionais durante a transição.
7. **Fase 6 — Página Análise:** multi-CSV, comparação real×simulação, pipeline
   passo a passo, Stefan-Boltzmann (A10), relatório PDF ampliado.
8. **Fase 7 — Simulação física melhor (A9)** e empacotamento: PyInstaller
   (`--windowed`, atenção aos hooks do QFluentWidgets/pyqtgraph) + script Inno Setup
   (fluxo que o usuário já domina), conforme `Markdowns/project_description.md` §5.6.

**Nota (pedido do usuário):** a teoria de erros (§6) deve ser IMPLEMENTADA no software
durante a reforma (Fase 3), mas o estudo conceitual do tema fica para depois — ao
trabalhar nessa fase, explique as escolhas (Tipo A/B, ponderação, k=2) nos commits e
em comentários didáticos, pois o usuário quer aprender com o código.

Cada fase deve terminar com o software abrindo e rodando uma simulação completa
(no modo mock a partir da Fase 1).

## 10. Referências dentro do repositório

> Estes documentos também aparecem na **aba Referências** do software, com o
> caminho oficial de acesso de cada um. A fonte de verdade é
> `Software/content/referencias.py` — para acrescentar um documento, edite essa
> lista; a UI se adapta sozinha.


- Teoria: `Docs/Corpo negro e determinação experimental da constante de Planck.pdf`
  (Eqs. 1–13; Tabela 1 mostra as incertezas típicas alcançáveis: h ≈ (5,8±0,3)×10⁻³⁴).
- Specs DMM: `Docs/Tektronix-DMM4050-and-DMM4040-Digital-Multimeter-Datasheet-8.pdf`
  (seção "DC Current" — tabela de exatidão por faixa).
- Specs fonte: `Docs/PWS4205, PWS4305, PWS4323, PWS4602, and PWS4721.pdf`
  (Tabela 1 — setting/readback de V e I).
- Especificação original de produto/UX: `Markdowns/project_description.md`.
- Constantes físicas: usar as CODATA já definidas em `utils/math_models.py`
  (h_ref = 6.62607015e-34 J·s exato no SI atual).
