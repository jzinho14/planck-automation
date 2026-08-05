# Planck-Automation v1.0: Protocolo de Automação e Análise Analítica

## 1. Descrição do Experimento (Fundamentação Física)
Este projeto visa a determinação experimental da constante de Planck ($h$) através da radiação de um filamento de tungstênio, modelado como um corpo negro, utilizando LEDs como sensores espectrais seletivos.

- **Aproximação de Wien:**  
  $I(\lambda, T) \approx \frac{2\pi c^2 h}{\lambda^5} e^{-\frac{hc}{\lambda k_B T}}$
- **Termometria por Resistência:**  
  Determinação de $T$ via $R(T) = R_0(1 + aT + bT^2)$.
- **Linearização:**  
  O cálculo de $h$ baseia-se na inclinação da reta no gráfico $\ln(I_{\text{led}}) \times 1/T$.

---

## 2. Ecossistema de Instrumentação (Hardware)
O software comunica-se com instrumentos de precisão via `PyVISA`:

- **Fonte Tektronix PWS4323:** Controle de aquecimento do filamento (0–12 V).
- **Multímetro Tektronix DMM 4050:** Leitura da fotocorrente (resolução de até 100 pA).
- **Protocolo:** `USBTMC` / Comandos `SCPI`(PWS4323 via USB Serial para USB A e DMM 4050 via RS232 conversor para USB A).

---

## 3. Arquitetura do Software (Estrutura de Abas)

### Aba 1: Simulação Teórica e Predição
- **Entrada de Parâmetros:** Comprimento de onda ($\lambda$), temperatura inicial/final e resistividade teórica.
- **Geração de Dados:** O software calcula a intensidade teórica de Planck para cada ponto.
- **Exportação:** Opção de salvar a simulação em `.csv` (ex: `simulacao_teorica.csv`) para posterior comparação.

### Aba 2: Controle e Coleta (Interface de Operação)
- **Auto-Scan de Hardware:** Identificação automática dos IDs `PWS4323` e `DMM4050` no *startup*.
- **Intertravamento de Segurança:** Bloqueio do experimento se os instrumentos forem desconectados ou se campos obrigatórios ($R_0$, $\lambda$) estiverem vazios.
- **Coleta Assíncrona:** Gráficos em tempo real sem travar a UI, com salvamento automático em subpastas de projeto (`CSV`/`JSON`).

### Aba 3: Reconstrução e Comparação Histórica
- **Multi-View:** Carregamento simultâneo de múltiplos arquivos (ex: `experimento_real.csv` vs `simulacao_teorica.csv`).
- **Análise de Desvio:** Sobreposição de curvas para identificar erros sistemáticos, como perdas térmicas ou luz ambiente.

### Aba 4: Processamento Analítico e Cálculo de $h$
Esta aba atua como um *Solver* matemático detalhado:
- **Processamento de Dados:** Leitura do `CSV` selecionado e aplicação das correções (ex: cálculo da resistência para encontrar $T$).
- **Exibição de Equações:** Apresentação formatada das fórmulas utilizadas no cálculo.
- **Resolução Passo a Passo:**
  - Cálculo de $1/T$.
  - Aplicação de Logaritmo Natural em $I_{\text{led}}$.
  - **Regressão Linear:** Cálculo da inclinação ($M$) por mínimos quadrados.
- **Resultado Final:** Exibição da constante de Planck medida ($h_{\text{exp}}$) e o erro percentual em relação ao valor da literatura ($h_{\text{lit}}$).

---

## 4. Gestão de Dados e Segurança
- **Persistência:** Cada experimento cria uma pasta contendo o `.json` (metadados e propriedades do *setup*) e o `.csv` (dados brutos).
- **Proteção de Voo:** Antes de cada *Run*, o software re-scaneia as portas USB para garantir que os instrumentos continuam online.

---

# 5. Arquitetura e Diretrizes de Interface (UX/UI com PySide6)

Substitui-se o legado Tkinter por **PySide6 (Qt for Python)**, garantindo renderização nativa, suporte robusto a threading assíncrono, estilização via QSS e integração profissional com o ecossistema científico. A interface segue o princípio *“clínico, mas acolhedor”*: prioriza a legibilidade dos dados, reduz a carga cognitiva do operador e mantém a robustez exigida por instrumentação de laboratório de precisão.

## 5.1 Filosofia de Design & Estrutura de Layout

* **Janela Principal (`QMainWindow`):** Barra superior fixa com painel de status de hardware (ícones de conexão, modo de operação, temperatura estimada), área central com `QTabWidget` e barra lateral colapsável (`QDockWidget`) para logs e ajuda.
* **Sistema de Abas Otimizado:** Cada aba ocupa 100% da área útil. Painéis de parâmetros usam `QScrollArea` contida para evitar redimensionamentos bruscos.
* **Feedback Global:** `QStatusBar` com mensagens contextuais (ex: *"DMM4050 conectado | Salvando em /data/exp_003"*) e notificações discretas para eventos críticos.
* **Segurança Visual:** Intertravamentos usam cores semânticas (🔴 bloqueio, 🟡 alerta, 🟢 pronto). Estados nunca piscam ou geram fadiga. Validação em tempo real (`QValidator`) e desabilitação contextual de botões (ex: "Iniciar Coleta" só ativa se hardware OK, $R_0$ e $\lambda$ preenchidos).

## 5.2 Componentes por Aba (Especificação PySide6)

| Aba | Widget Principal | Funcionalidade Chave |
| :--- | :--- | :--- |
| **1. Simulação Teórica** | `QGroupBox` + `QDoubleSpinBox` + `GraphicsLayoutWidget` (pyqtgraph) | Inputs validados em tempo real, geração síncrona de curva de Wien, exportação `.csv` via `QFileDialog`. |
| **2. Controle e Coleta** | `QStackedWidget` + `QThread` + `QProgressBar` | Painel de intertravamento com LEDs de estado, gráficos assíncronos via *signal/slot*, botão de emergência destacado e acessível por atalho. |
| **3. Reconstrução** | `QListWidget` + pyqtgraph (*multi-curve*) | *Drag-and-drop* de arquivos, toggle de visibilidade por LED/LED, cálculo de desvio com painel de métricas (`QTableWidget` estilizado). |
| **4. Processamento Analítico** | `QScrollArea` + `QTextBrowser` (Markdown/HTML) | *Pipeline* de cálculos em cards expansíveis, regressão linear plotada, resultado final em `QFrame` com borda de destaque e erro percentual em *badge*. |

## 5.3 Sistema Auto-Instrucional & Acessibilidade

* **Contexto "?" Inteligente:** Ícones de ajuda abrem um `QDockWidget` lateral com guias visuais: montagem física, física quântica por trás das equações, significado de cada parâmetro e fluxo de operação seguro.
* **`Qt.QWhatsThis` & Tooltips Ricos:** Cada campo e botão possui explicação técnica sob demanda. Fórmulas são exibidas com formatação clara (Unicode/HTML).
* **Acessibilidade Nativa:** Navegação completa por teclado (`Tab`, `Enter`, `Esc`), alto contraste opcional, fontes escaláveis (base 14px, monospace para dados numéricos) e suporte a leitores de tela via `accessibleName`.

## 5.4 Integração com Backend & Threading Assíncrono

* **`HardwareManager(QObject)`:** Centraliza PyVISA, emite sinais `connected()`, `error(msg)`, `data_ready(df)` e é instanciada na thread principal.
* **Execução Não-Bloqueante:** Leituras de hardware (PyVISA) e cálculos de regressão rodam em `QThread`/`QRunnable`, comunicando-se com a UI via `pyqtSignal`. A interface nunca congela.
* **Proteção de Voo:** Antes de cada *Run*, o software re-scaneia portas USB para garantir que PWS4323 e DMM4050 continuam online. Falha aborta a coleta com log automático.

## 5.5 Estética & Tema (QSS)

* **Paleta:** Fundo `#F8F9FA` (light mode), cards `#FFFFFF` com sombra sutil, acentos em `#0066CC` (ações primárias) e `#10B981` (sucesso). *Dark mode* toggle para sessões noturnas.
* **Tipografia:** *Inter* ou *Segoe UI* para UI, *JetBrains Mono* / *Roboto Mono* para valores e logs. Hierarquia: títulos 16px bold, corpo 14px, dados 13px monospace.
* **Gráficos:** pyqtgraph integrado, eixos limpos, grid discreto (`#E5E7EB`), cores por LED pré-definidas, legendas interativas e zoom/pan nativos.
* **Consistência:** Espaçamento 8px/16px (sistema 8pt), botões `border-radius: 4px`, estados *hover*/*pressed* via QSS. Zero gradientes agressivos ou ícones decorativos.

## 5.6 Compilação, Distribuição & Deploy (.exe + Inno Setup)

* **Empacotamento:** `PyInstaller --windowed --onefile main.py` para gerar o executável isolado.
* **Inno Setup Script:** Compilação do instalador `.exe` profissional com:
  * Instalação silenciosa opcional (`/VERYSILENT /SUPPRESSMSGBOXES`)
  * Criação de atalhos no Desktop/Start Menu
  * Registro de extensão `.json`/`.csv` para abertura direta pelo software
  * *Uninstaller* limpo e verificação de dependências (*VC++ Redistributable*)
* **Persistência Visual:** `QSettings` salva preferências (últimos caminhos, tema, aba ativa). O instalador mantém a identidade visual nativa em Windows e oferece fallback automático para Linux/macOS.

## 5.7 Notas de Implementação & Dicas Rápidas

* **Gráficos em Tempo Real:** Prefira `pyqtgraph` a `matplotlib` na Aba 2. Otimizado para atualização assíncrona e consome ~10x menos CPU durante varreduras longas.
* **Renderização de Fórmulas:** `QTextBrowser` não suporta LaTeX nativo. Use HTML + Unicode (`&lambda;`, `&sum;`, `&nbsp;`) ou embuta `matplotlib.figure` como `FigureCanvasQTAgg` para equações complexas na Aba 4.
* **Gerenciamento de Estado:** Centralize a lógica de hardware em uma classe `QObject` com sinais. Nunca acesse widgets de hardware diretamente de threads secundárias.
* **QSS Centralizado:** Mantenha um arquivo `theme.qss` único. Carregue no `__init__` do `QApplication`:
  ```python
  with open("theme.qss", "r") as f:
      app.setStyleSheet(f.read())