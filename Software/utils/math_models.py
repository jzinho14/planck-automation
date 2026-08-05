# utils/math_models.py
import numpy as np

# Constantes Físicas Fundamentais (CODATA)
C = 299792458.0              # Velocidade da luz (m/s)
K_B = 1.380649e-23           # Constante de Boltzmann (J/K)
H_REF = 6.62607015e-34       # Constante de Planck de referência (J.s)
E_CHARGE = 1.602176634e-19   # Carga elementar (C)

def calculate_temperature(R_array: np.ndarray, R0: float, alpha: float, beta: float) -> np.ndarray:
    """
    Calcula a temperatura (K) do filamento a partir da sua resistência.
    Resolve a equação quadrática: R(T) = R0 * (1 + alpha*T + beta*T^2)
    Utiliza a fórmula de Bhaskara para encontrar a raiz física (positiva).
    """
    # R0*beta*T^2 + R0*alpha*T + (R0 - R) = 0
    a = R0 * beta
    b = R0 * alpha
    c = R0 - R_array
    
    delta = b**2 - 4 * a * c
    
    # Apenas a raiz que faz sentido físico (T > 0 e crescente com R)
    T_celsius = (-b + np.sqrt(delta)) / (2 * a)
    T_kelvin = T_celsius + 273.15
    return T_kelvin

def simulate_experiment_data(voltages: np.ndarray, R0: float, alpha: float, beta: float, 
                             lambda_led_nm: float, noise_level: float = 0.05) -> tuple:
    lambda_led = lambda_led_nm * 1e-9
    
    T_kelvin = np.linspace(1500, 3000, len(voltages))
    T_celsius = T_kelvin - 273.15
    R_filament = R0 * (1 + alpha * T_celsius + beta * T_celsius**2)
    current_filament = voltages / R_filament
    
    A_proportionality = 1e-5 
    exponent = - (H_REF * C) / (lambda_led * K_B * T_kelvin)
    ideal_photocurrent = A_proportionality * (1 / lambda_led**5) * np.exp(exponent)
    
    # CORREÇÃO: Ruído proporcional ao sinal medido + um piso instrumental do DMM (ex: 100 pA)
    piso_dmm = 1e-10
    noise = np.random.normal(0, noise_level * ideal_photocurrent + piso_dmm, size=len(voltages))
    noisy_photocurrent = ideal_photocurrent + noise
    
    # Clipamos os valores muito negativos para não quebrar o logaritmo, limitando ao piso do DMM
    noisy_photocurrent = np.clip(noisy_photocurrent, a_min=piso_dmm, a_max=None)
    
    return voltages, current_filament, R_filament, T_kelvin, noisy_photocurrent

def calculate_planck_constant(T_kelvin: np.ndarray, photocurrent: np.ndarray, lambda_led_nm: float) -> tuple:
    lambda_led = lambda_led_nm * 1e-9
    x = 1 / T_kelvin
    
    # CORREÇÃO: Filtro de Regressão. Só usamos pontos onde a corrente é pelo menos 10x maior que o piso de ruído
    limiar_confianca = 1e-9 # 1 nA
    valid_indices = photocurrent > limiar_confianca
    
    x_valid = x[valid_indices]
    y_valid = np.log(photocurrent[valid_indices])
    
    if len(x_valid) < 2:
        return 0, 0, 0, 0, 0
    
    A = np.vstack([x_valid, np.ones(len(x_valid))]).T
    m, c = np.linalg.lstsq(A, y_valid, rcond=None)[0]
    
    y_pred = m * x_valid + c
    ss_res = np.sum((y_valid - y_pred)**2)
    ss_tot = np.sum((y_valid - np.mean(y_valid))**2)
    r_squared = 1 - (ss_res / ss_tot)
    
    h_experimental = - (m * lambda_led * K_B) / C
    erro_relativo = abs(h_experimental - H_REF) / H_REF * 100
    
    return h_experimental, erro_relativo, m, c, r_squared
    """
    Realiza a regressão linear de ln(I) vs 1/T para extrair a constante de Planck experimental.
    Retorna: (h_experimental, erro_relativo, coef_angular, coef_linear, r_squared)
    """
    lambda_led = lambda_led_nm * 1e-9
    
    # Preparando as variáveis linearizadas
    x = 1 / T_kelvin
    
    # Tratamento para evitar log de zero ou negativo
    valid_indices = photocurrent > 1e-12
    x_valid = x[valid_indices]
    y_valid = np.log(photocurrent[valid_indices])
    
    if len(x_valid) < 2:
        return 0, 0, 0, 0, 0
    
    # Ajuste linear: y = mx + c
    A = np.vstack([x_valid, np.ones(len(x_valid))]).T
    m, c = np.linalg.lstsq(A, y_valid, rcond=None)[0]
    
    # Calculando o R^2 para avaliar a qualidade do ajuste
    y_pred = m * x_valid + c
    ss_res = np.sum((y_valid - y_pred)**2)
    ss_tot = np.sum((y_valid - np.mean(y_valid))**2)
    r_squared = 1 - (ss_res / ss_tot)
    
    # Extraindo h da inclinação (m = -hc / (\lambda * k_B))
    h_experimental = - (m * lambda_led * K_B) / C
    erro_relativo = abs(h_experimental - H_REF) / H_REF * 100
    
    return h_experimental, erro_relativo, m, c, r_squared