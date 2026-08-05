import pyvisa
import time # Certifique-se de que o time está importado aqui no topo
from PySide6.QtCore import QObject, QSettings, QThread, Signal

from core.mock_hardware import (MockPWS4323_Driver, MockDMM4050_Driver,
                                STRING_RECURSO_PWS, STRING_RECURSO_DMM)

# --- CONFIGURAÇÃO PERSISTENTE ---
# Nome da organização/aplicação do QSettings, num só lugar em vez de repetido
# como string mágica em cada arquivo que precisa ler a configuração.
ORGANIZACAO = "Senac"
APLICACAO = "PlanckAutomation"
CHAVE_MODO_DEMONSTRACAO = "Connection/DemoMode"

# B5 — o endereço do multímetro deixa de ser constante no código.
CHAVE_IP_DMM = "Connection/DMMIp"
CHAVE_PORTA_DMM = "Connection/DMMPorta"
IP_DMM_PADRAO = "192.168.1.107"
PORTA_DMM_PADRAO = "3490"

# B4 — o limite de corrente deixa de ser hardcoded. O padrão é o valor
# conservador que o comentário do código antigo mencionava; o valor efetivo
# para o filamento em uso é decisão de bancada (ver PENDENCIAS.txt, P3).
CHAVE_LIMITE_CORRENTE = "Safety/LimiteCorrenteA"
LIMITE_CORRENTE_PADRAO = 1.5


def preferencias() -> QSettings:
    return QSettings(ORGANIZACAO, APLICACAO)


def endereco_dmm() -> str:
    """String de recurso VISA do multímetro, montada a partir das preferências."""
    cfg = preferencias()
    ip = cfg.value(CHAVE_IP_DMM, IP_DMM_PADRAO)
    porta = cfg.value(CHAVE_PORTA_DMM, PORTA_DMM_PADRAO)
    return f"TCPIP::{ip}::{porta}::SOCKET"


def limite_corrente() -> float:
    """Limite de corrente da fonte configurado pelo operador (A)."""
    try:
        return float(preferencias().value(CHAVE_LIMITE_CORRENTE, LIMITE_CORRENTE_PADRAO))
    except (TypeError, ValueError):
        return LIMITE_CORRENTE_PADRAO


def modo_demonstracao_ativo() -> bool:
    """Modo demonstração: o software roda com a bancada simulada, sem VISA."""
    return preferencias().value(CHAVE_MODO_DEMONSTRACAO, False, type=bool)


def obter_drivers(modo_demonstracao: bool) -> tuple:
    """
    Escolhe o par de drivers conforme o modo.

    Os mocks têm a mesma interface dos reais, então quem consome não precisa
    saber qual dos dois recebeu — só instancia e usa.
    """
    if modo_demonstracao:
        return MockPWS4323_Driver, MockDMM4050_Driver
    return PWS4323_Driver, DMM4050_Driver


# --- DRIVERS SCPI DOS INSTRUMENTOS ---

class PWS4323_Driver:
    def __init__(self, resource_manager, resource_string):
        self.inst = resource_manager.open_resource(resource_string)
        self.inst.timeout = 5000
        self.inst.write("*CLS") # Comando universal para limpar erros anteriores
        
    def configure_safety_limits(self, max_current: float = 1.0):
        self.inst.write(f"SOUR:CURR {max_current}")
        
    def set_output(self, state: bool):
        comando = "ON" if state else "OFF"
        self.inst.write(f"OUTP {comando}")
        
    def set_voltage(self, volts: float):
        self.inst.write(f"SOUR:VOLT {volts}")
        
    def measure_current(self) -> float:
        # Pede a leitura da corrente e converte
        return float(self.inst.query("MEAS:CURR?"))

    def measure_voltage(self) -> float:
        """
        Tensão realmente presente nos terminais (A4).

        Não é o mesmo que a tensão programada: o readback do PWS4323 é mais
        exato que a exatidão de programação, então R = V/i calculado com este
        valor carrega menos erro do que com o setpoint.
        """
        return float(self.inst.query("MEAS:VOLT?"))

    def turn_off_safely(self):
        try:
            self.inst.write("SOUR:VOLT 0.0")
            import time
            time.sleep(0.1)
            self.set_output(False)
        except:
            pass

    def close(self):
        self.turn_off_safely()
        self.inst.close()


class DMM4050_Driver:
    def __init__(self, resource_manager, resource_string):
        self.inst = resource_manager.open_resource(resource_string)
        self.inst.timeout = 10000 
        
        if "SOCKET" in resource_string.upper():
            self.inst.write_termination = '\n'
            self.inst.read_termination = '\n'
            
        # --- A ORDEM AQUI É CRÍTICA ---
        self.inst.write("SYST:REM") # 1. Força o multímetro a entrar em Modo Remoto
        time.sleep(0.1)
        self.inst.write("*CLS")     # 2. Limpa o buffer de erros
        time.sleep(0.1)
        
    def configure_dc_current(self, nplc: float = 10.0):
        self.inst.write("CONF:CURR:DC")
        time.sleep(0.1) 
        
        # --- NOVA LINHA CRÍTICA ---
        # Força a escala mínima de 100 uA. Sem isto, o Auto-Range esconde os nanoamperes!
        self.inst.write("SENS:CURR:DC:RANG 1e-4") 
        time.sleep(0.1)
        
        self.inst.write(f"SENS:CURR:DC:NPLC {nplc}")
        time.sleep(0.1)
        
    def read_current(self) -> float:
        # 3. Dispara a leitura e busca o resultado
        return float(self.inst.query("READ?"))

    def close(self):
        # 4. Devolve o controle para o painel frontal antes de fechar a comunicação
        try:
            self.inst.write("SYST:LOC")
        except:
            pass
        self.inst.close()

class ScannerThread(QThread):
    # Agora emite listas de tuplas: [(nome_exibicao, resource_string), ...]
    resources_found = Signal(list, list)

    def run(self):
        # Em modo demonstração não há barramento para varrer: oferecemos os
        # dois instrumentos simulados e saímos.
        if modo_demonstracao_ativo():
            self.resources_found.emit(
                [("PWS4323 (simulado)", STRING_RECURSO_PWS)],
                [("DMM4050 (simulado)", STRING_RECURSO_DMM)],
            )
            return

        try:
            rm = pyvisa.ResourceManager('@ivi')
            resources = rm.list_resources()
        except Exception:
            resources = []

        pws_items = []
        dmm_items = []
        
        # 1. Busca por USB (PWS)
        for res in resources:
            if "USB" in res.upper() and "0699" in res:
                pws_items.append((f"PWS4323 (USB)", res))
                break  # Pega apenas o primeiro PWS encontrado

        # 2. Fallback manual para DMM via SOCKET. O endereço vem das
        #    preferências, editável na página de Conexão (B5).
        dmm_res = endereco_dmm()
        rotulo_dmm = dmm_res.split("::")[1] + ":" + dmm_res.split("::")[2]

        try:
            # Testa rápido se o DMM está na rede antes de listar
            rm_test = pyvisa.ResourceManager('@ivi')
            dmm_test = rm_test.open_resource(dmm_res, timeout=500)
            dmm_test.write_termination = '\n'
            dmm_test.read_termination = '\n'
            dmm_test.query('*IDN?')
            dmm_test.close()
            dmm_items.append((f"DMM4050 ({rotulo_dmm})", dmm_res))
        except Exception:
            # Se falhar, ainda adiciona para o usuário tentar conectar/corrigir
            dmm_items.append((f"DMM4050 (Desconectado/Manual)", dmm_res))
                
        self.resources_found.emit(pws_items, dmm_items)


class ValidatorThread(QThread):
    validation_result = Signal(str, bool, str)

    def __init__(self, device_id: str, resource_string: str):
        super().__init__()
        self.device_id = device_id
        self.resource_string = resource_string

    def run(self):
        if not self.resource_string:
            self.validation_result.emit(self.device_id, False, "Recurso vazio")
            return

        # Instrumento simulado: responde o *IDN? sem passar por VISA.
        if self.resource_string.upper().startswith("DEMO::"):
            self.validation_result.emit(
                self.device_id, True,
                "SIMULADO,Bancada virtual,modo demonstracao,-"
            )
            return

        try:
            rm = pyvisa.ResourceManager('@ivi')
            inst = rm.open_resource(self.resource_string)
            inst.timeout = 1500
            
            # Configuração crucial para conexões via rede (SOCKET)
            if "SOCKET" in self.resource_string.upper():
                inst.write_termination = '\n'
                inst.read_termination = '\n'
                
            idn = inst.query('*IDN?')
            inst.close()
            self.validation_result.emit(self.device_id, True, idn.strip())
        except Exception as e:
            self.validation_result.emit(self.device_id, False, str(e))


class HardwareManager(QObject):
    resources_found = Signal(list, list)
    validation_result = Signal(str, bool, str)

    def __init__(self):
        super().__init__()
        self._scanner = None
        self._validators = []

    def scan_resources(self):
        # Um scan de cada vez. Reatribuir self._scanner com uma varredura ainda
        # em curso largava a última referência à QThread anterior, e destruir um
        # QThread em execução é o mesmo problema tratado em B8 — aqui agravado
        # porque o ScannerThread pode ficar segundos preso no open_resource do
        # DMM. Enquanto uma varredura corre, novos cliques são ignorados.
        if self._scanner is not None and self._scanner.isRunning():
            return

        self._scanner = ScannerThread()
        self._scanner.resources_found.connect(self.resources_found.emit)
        self._scanner.finished.connect(self._discard_scanner)
        self._scanner.start()

    def _discard_scanner(self):
        """Solta a referência do ScannerThread terminado, liberando novo scan."""
        scanner = self.sender()
        if scanner is None:
            return
        scanner.wait()
        if self._scanner is scanner:
            self._scanner = None

    def validate_connection(self, device_id: str, resource_string: str):
        validator = ValidatorThread(device_id, resource_string)
        validator.validation_result.connect(self.validation_result.emit)

        # A referência tem de ser mantida enquanto a thread corre (sem ela o
        # garbage collector destruiria o QThread em execução), mas tem de ser
        # solta quando ela termina — ver B8.
        self._validators.append(validator)
        validator.finished.connect(self._discard_validator)

        validator.start()

    def _discard_validator(self):
        """
        Solta a referência de um ValidatorThread já terminado (B8).

        Ligado a um método do HardwareManager (que vive na thread da UI), o
        Qt usa conexão em fila: este slot corre na thread da UI, então mexer
        na lista é seguro. O wait() garante que a thread saiu de facto antes
        de largarmos a última referência a ela.
        """
        validator = self.sender()
        if validator is None:
            return
        validator.wait()
        if validator in self._validators:
            self._validators.remove(validator)