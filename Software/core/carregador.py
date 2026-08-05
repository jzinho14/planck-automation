# core/carregador.py
"""
Leitura de coletas gravadas (Fase 6).

Uma coleta é o par CSV + JSON de metadados. O JSON só existe a partir da
Fase 4, então este módulo precisa lidar com três gerações de arquivo:

  1. **Histórica** (5 colunas, sem JSON) — os 52 arquivos de `data_backup/`.
     Não dizem com que parâmetros foram processados; o que se sabe deles é o
     que está nas próprias colunas.
  2. **Fase 2** (6 colunas: ganhou `Tensao_Medida_V`).
  3. **Fase 3+** (8 colunas: ganhou desvio Tipo A e nº de leituras) + JSON.

A regra que tornou isso possível: colunas novas sempre entraram AO FINAL, e as
cinco originais nunca mudaram de ordem.
"""
import csv
import glob
import os
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from core import metadados

COLUNAS_HISTORICAS = ["Tensao_Fonte_V", "Corrente_Filamento_A", "Resistencia_Ohms",
                      "Temperatura_K", "Fotocorrente_A"]


@dataclass
class Coleta:
    """Uma coleta lida do disco, com o que se sabe sobre ela."""

    caminho: str
    tensao_fonte: np.ndarray
    corrente: np.ndarray
    resistencia: np.ndarray
    temperatura: np.ndarray
    fotocorrente: np.ndarray
    tensao_medida: np.ndarray = None      # None nas coletas históricas
    desvio_fotocorrente: np.ndarray = None
    meta: dict = field(default_factory=dict)

    @property
    def nome(self) -> str:
        return Path(self.caminho).stem

    @property
    def simulada(self) -> bool:
        if self.meta.get("modo"):
            return self.meta["modo"] == "demonstracao"
        return Path(self.caminho).name.startswith("demo_")

    @property
    def n_pontos(self) -> int:
        return int(self.tensao_fonte.size)

    @property
    def tem_metadados(self) -> bool:
        return bool(self.meta)

    @property
    def geracao(self) -> str:
        if self.desvio_fotocorrente is not None:
            return "Fase 3+"
        if self.tensao_medida is not None:
            return "Fase 2"
        return "histórica"

    @property
    def potencia(self) -> np.ndarray:
        """V·i — a potência dissipada, usada na verificação de Stefan-Boltzmann."""
        tensao = self.tensao_medida if self.tensao_medida is not None else self.tensao_fonte
        return tensao * self.corrente

    def descricao(self) -> str:
        tipo = "simulada" if self.simulada else "real"
        marca = "" if self.tem_metadados else "  ⚠ sem metadados"
        return (f"{self.nome}  ·  {self.n_pontos} pontos  ·  {tipo}  ·  "
                f"{self.geracao}{marca}")

    def parametros_conhecidos(self) -> dict:
        """
        O que os metadados dizem sobre como esta coleta foi obtida.

        Numa coleta histórica devolve vazio — e é exatamente esse buraco que os
        metadados da Fase 4 vieram tapar.
        """
        if not self.meta:
            return {}
        filamento = self.meta.get("filamento_medido", {})
        sensor = self.meta.get("sensor", {})
        return {
            "r0": filamento.get("r0_corrigido_ohm"),
            "u_r0": filamento.get("incerteza_r0_ohm"),
            "alpha": filamento.get("alpha_por_kelvin"),
            "beta": filamento.get("beta_por_kelvin2"),
            "lam": sensor.get("lambda_nm"),
            "delta_lam": sensor.get("delta_lambda_nm"),
            "r_cabos": filamento.get("resistencia_cabos_ohm"),
            "perfil_led": self.meta.get("perfis", {}).get("led"),
            "perfil_filamento": self.meta.get("perfis", {}).get("filamento"),
        }


def _coluna(linhas: list, nome: str):
    if nome not in linhas[0]:
        return None
    indice = linhas[0].index(nome)
    valores = []
    for linha in linhas[1:]:
        if len(linha) <= indice:
            valores.append(np.nan)
            continue
        try:
            valores.append(float(linha[indice]))
        except ValueError:
            valores.append(np.nan)
    return np.array(valores, dtype=float)


def carregar(caminho: str) -> Coleta:
    """
    Lê uma coleta. Levanta ValueError se o arquivo não for uma coleta válida.

    A leitura é por NOME de coluna, não por posição — assim um arquivo com
    colunas novas no meio (que não deveria existir, mas...) ainda funciona.
    """
    with open(caminho, newline="", encoding="utf-8") as arquivo:
        linhas = [linha for linha in csv.reader(arquivo) if linha]

    if len(linhas) < 2:
        raise ValueError("arquivo sem dados")

    faltando = [c for c in COLUNAS_HISTORICAS if c not in linhas[0]]
    if faltando:
        raise ValueError(f"não parece uma coleta: faltam {', '.join(faltando)}")

    return Coleta(
        caminho=caminho,
        tensao_fonte=_coluna(linhas, "Tensao_Fonte_V"),
        corrente=_coluna(linhas, "Corrente_Filamento_A"),
        resistencia=_coluna(linhas, "Resistencia_Ohms"),
        temperatura=_coluna(linhas, "Temperatura_K"),
        fotocorrente=_coluna(linhas, "Fotocorrente_A"),
        tensao_medida=_coluna(linhas, "Tensao_Medida_V"),
        desvio_fotocorrente=_coluna(linhas, "Desvio_Fotocorrente_A"),
        meta=metadados.ler(caminho),
    )


def listar(pasta: str = "data_backup") -> list:
    """Caminhos de todas as coletas da pasta, mais recentes primeiro."""
    arquivos = glob.glob(os.path.join(pasta, "*.csv"))
    return sorted(arquivos, key=os.path.getmtime, reverse=True)


def carregar_varias(caminhos: list) -> tuple:
    """
    Carrega vários arquivos, devolvendo (coletas, problemas).

    Um arquivo ruim no meio da lista não impede os outros de carregarem — a
    página de Análise mostra os problemas em separado.
    """
    coletas, problemas = [], []
    for caminho in caminhos:
        try:
            coletas.append(carregar(caminho))
        except (ValueError, OSError, UnicodeDecodeError) as erro:
            problemas.append(f"{Path(caminho).name}: {erro}")
    return coletas, problemas
