# core/metadados.py
"""
Metadados de cada coleta, gravados em JSON ao lado do CSV (Fase 4).

Por que isto existe
-------------------
O CSV guarda as medidas, mas não guardava COM QUE PARÂMETROS elas foram
processadas. Um arquivo antigo não dizia qual R0, quais coeficientes ou qual
LED estavam em uso. O custo disso foi concreto: para calibrar a bancada
simulada foi preciso DEDUZIR, a partir dos próprios números, que as coletas
históricas tinham usado R0 ≈ 0,42 Ω. Isso não deve voltar a acontecer.

A partir daqui, cada coleta produz dois arquivos irmãos:

    data_backup/exp_planck_20260805_143000.csv     ← as medidas
    data_backup/exp_planck_20260805_143000.json    ← como foram obtidas

O JSON é escrito duas vezes: uma ao ABRIR a coleta (para que, se faltar
energia no meio, os parâmetros já estejam registrados) e outra ao FECHAR,
acrescentando os resultados. Nunca é reescrito por outra coleta.
"""
import json
import platform
import sys
from datetime import datetime
from pathlib import Path

VERSAO_ESQUEMA = 1


def caminho_para(csv_path: str) -> Path:
    """O JSON irmão de um CSV de coleta."""
    return Path(csv_path).with_suffix(".json")


def _ambiente() -> dict:
    return {
        "python": sys.version.split()[0],
        "sistema": f"{platform.system()} {platform.release()}",
        "maquina": platform.node(),
    }


def montar_abertura(params: dict, modo_demonstracao: bool,
                    dmm_res: str, pws_res: str) -> dict:
    """
    Bloco gravado no início da coleta: tudo que se sabe antes de medir.

    Separa PERFIS (o que veio de catálogo) de MEDIDO (o que é desta montagem
    específica) e de VARREDURA, para que a leitura seja óbvia meses depois.
    """
    return {
        "esquema": VERSAO_ESQUEMA,
        "iniciado_em": datetime.now().astimezone().isoformat(timespec="seconds"),
        "modo": "demonstracao" if modo_demonstracao else "bancada_real",
        "instrumentos": {
            "fonte": pws_res,
            "multimetro": dmm_res,
        },
        "perfis": {
            "led": params.get("perfil_led"),
            "filamento": params.get("perfil_filamento"),
            "varredura": params.get("perfil_varredura"),
        },
        "filamento_medido": {
            "resistencia_a_frio_ohm": params.get("r_frio"),
            "incerteza_resistencia_a_frio_ohm": params.get("u_r_frio"),
            "temperatura_ambiente_c": params.get("t_ambiente"),
            "r0_corrigido_ohm": params.get("r0"),
            "incerteza_r0_ohm": params.get("u_r0"),
            "alpha_por_kelvin": params.get("alpha"),
            "beta_por_kelvin2": params.get("beta"),
            "resistencia_cabos_ohm": params.get("r_cabos"),
        },
        "sensor": {
            "lambda_nm": params.get("lam"),
            "delta_lambda_nm": params.get("delta_lam"),
        },
        "varredura": {
            "tensao_inicial_v": params.get("v_start"),
            "tensao_final_v": params.get("v_end"),
            "passo_v": params.get("v_step"),
            "estabilizacao_ms": params.get("delay"),
            "leituras_por_ponto": params.get("n_leituras"),
            "temperatura_minima_regressao_k": params.get("t_minima"),
        },
        "ambiente": _ambiente(),
        "resultado": None,   # preenchido ao encerrar
    }


def montar_resultado(resultado) -> dict:
    """Bloco de resultados, a partir de um ResultadoAnalise."""
    return {
        "h_j_s": resultado.h,
        "incerteza_padrao_j_s": resultado.u_h,
        "incerteza_expandida_j_s": resultado.incerteza_expandida,
        "fator_abrangencia_k": resultado.k,
        "texto": resultado.texto,
        "erro_relativo_pct": resultado.erro_relativo,
        "compativel_com_codata": bool(resultado.compativel_com_codata),
        "ajuste": {
            "inclinacao": resultado.ajuste.m,
            "incerteza_inclinacao": resultado.ajuste.u_m,
            "intercepto": resultado.ajuste.c,
            "incerteza_intercepto": resultado.ajuste.u_c,
            "r2": resultado.ajuste.r2,
            "chi2_reduzido": resultado.ajuste.chi2_reduzido,
            "iteracoes": resultado.ajuste.iteracoes,
        },
        "pontos": {
            "coletados": resultado.n_total,
            "usados_na_regressao": resultado.n_usados,
        },
        "orcamento_incerteza_h_pct": dict(resultado.orcamento_ordenado()),
        "orcamento_incerteza_temperatura_pct": resultado.orcamento_temperatura,
        "h_nao_ponderado_j_s": resultado.h_nao_ponderado,
    }


def gravar(csv_path: str, dados: dict) -> Path:
    """
    Escreve o JSON de metadados. Nunca deixa uma falha aqui derrubar a coleta.

    Perder os metadados é ruim; perder as medidas por causa dos metadados seria
    muito pior. Por isso o erro é engolido e reportado no retorno.
    """
    destino = caminho_para(csv_path)
    try:
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(
            json.dumps(dados, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8")
    except OSError:
        return None
    return destino


def ler(csv_path: str) -> dict:
    """Lê os metadados de uma coleta; devolve {} se não houver."""
    origem = caminho_para(csv_path)
    if not origem.is_file():
        return {}
    try:
        return json.loads(origem.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
