import pyvisa
import time # Certifique-se de que o time está importado aqui no topo
from PySide6.QtCore import QObject, QThread, Signal

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

        # 2. Fallback manual para DMM via SOCKET
        DMM_IP = "192.168.1.107"
        DMM_PORT = "3490"
        dmm_res = f"TCPIP::{DMM_IP}::{DMM_PORT}::SOCKET"
        
        try:
            # Testa rápido se o DMM está na rede antes de listar
            rm_test = pyvisa.ResourceManager('@ivi')
            dmm_test = rm_test.open_resource(dmm_res, timeout=500)
            dmm_test.write_termination = '\n'
            dmm_test.read_termination = '\n'
            dmm_test.query('*IDN?')
            dmm_test.close()
            dmm_items.append((f"DMM4050 ({DMM_IP}:{DMM_PORT})", dmm_res))
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
        self._scanner = ScannerThread()
        self._scanner.resources_found.connect(self.resources_found.emit)
        self._scanner.start()

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