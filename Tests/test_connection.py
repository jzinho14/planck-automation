import pyvisa

def scan_instruments_for_ui():
    rm = pyvisa.ResourceManager('@ivi')
    pws_items, dmm_items = [], []

    # 1. Auto-scan (funciona bem para USB)
    for res in rm.list_resources():
        if "USB" in res and "0699" in res:
            pws_items.append((f"PWS4323 (USB)", res))
            break  # Pega apenas o primeiro PWS encontrado

    # 2. Fallback manual para DMM (SOCKET não é auto-descoberto pelo NI-VISA)
    # Você pode trocar este IP/porta por um campo de input na interface depois
    DMM_IP = "192.168.1.107"
    DMM_PORT = "3490"
    dmm_res = f"TCPIP::{DMM_IP}::{DMM_PORT}::SOCKET"
    
    try:
        dmm_test = rm.open_resource(dmm_res, timeout=1500)
        dmm_test.write_termination = '\n'
        dmm_test.read_termination = '\n'
        idn = dmm_test.query('*IDN?').strip()
        dmm_test.close()
        dmm_items.append((f"DMM4050 ({DMM_IP}:{DMM_PORT})", dmm_res))
    except Exception:
        # Se falhar, ainda adiciona para o usuário tentar conectar manualmente
        dmm_items.append((f"DMM4050 (Manual: {DMM_IP}:{DMM_PORT})", dmm_res))

    return pws_items, dmm_items

if __name__ == "__main__":
    pws, dmm = scan_instruments_for_ui()
    print("📦 PWS:", pws)
    print("📦 DMM:", dmm)