# utils/stefan_boltzmann.py
"""
Verificação da lei de Stefan-Boltzmann (achado A10).

O artigo de referência não se limita a extrair h: ele usa a mesma montagem para
verificar que a potência irradiada cresce com a quarta potência da temperatura.
É um teste independente, e os CSVs já contêm tudo que ele precisa — só faltava
alguém fazer a conta.

A ideia
-------
Em regime estacionário, a potência elétrica entregue ao filamento é dissipada.
Quando a radiação domina (a 2500 K ela responde por ~99% da dissipação, medido
sobre os dados reais):

    P = V·i = ε σ A (T⁴ − T_amb⁴) ≈ ε σ A T⁴                        (S1)

Tomando o logaritmo dos dois lados:

    log(P) = log(ε σ A) + 4·log(T)                                  (S2)

Ou seja: **log(V·i) contra log(T) é uma reta de inclinação 4**. A inclinação
medida é o resultado do teste; o quanto ela se afasta de 4 diz o quanto a
aproximação de corpo cinza e o domínio da radiação se sustentam na montagem.

O que os dados desta bancada mostram
-----------------------------------
Rodando a verificação sobre os CSVs reais de `data_backup/`, acima de 1800 K, o
expoente sai entre **4,06 e 4,47**, com R² entre 0,99 e 1,000.

Ele fica sistematicamente **um pouco ACIMA de 4**, e isso é físico, não erro: o
tungstênio não é corpo negro, e sua emissividade **cresce** com a temperatura.
Como o que se mede é ε(T)·T⁴, um ε crescente faz a potência subir mais rápido
que T⁴ e empurra o expoente para cima.

Na direção oposta atuam condução e convecção, que seguem aproximadamente
(T−T₀) e não T⁴. Elas puxam o expoente para BAIXO e pesam tanto mais quanto
mais frio o ponto — daí a necessidade do corte de temperatura mínima. Numa
faixa fria demais o expoente despenca.

Como julgar o resultado
-----------------------
**Não por um teste de sigmas.** A incerteza estatística da inclinação é
minúscula aqui: a exatidão de V e i dá u_P/P da ordem de 0,1%, o que produz
barra de erro de ±0,02 no expoente. Contra isso, qualquer desvio real vira
"muitos sigmas" e o teste reprovaria sempre.

O desvio observado é SISTEMÁTICO (emissividade), não aleatório. O critério
honesto é o **desvio relativo**: a quantos por cento de 4 está o expoente? Até
~10% a montagem se comporta como a teoria prevê para um corpo cinza real.
"""
from dataclasses import dataclass

import numpy as np

from utils.error_models import ajuste_linear_ponderado
from utils.math_models import TEMPERATURA_MINIMA_PADRAO

EXPOENTE_TEORICO = 4.0

# Até quantos por cento de 4 a montagem ainda é considerada coerente com a
# teoria para um corpo cinza real (ver o cabeçalho do módulo).
TOLERANCIA_RELATIVA_PCT = 10.0


@dataclass
class ResultadoStefanBoltzmann:
    """O que a verificação produz."""

    expoente: float             # a inclinação medida
    u_expoente: float
    intercepto: float
    r2: float
    n_pontos: int
    n_total: int
    t_minima: float
    log_temperatura: np.ndarray = None
    log_potencia: np.ndarray = None
    mascara: np.ndarray = None

    @property
    def desvio_relativo(self) -> float:
        """Distância percentual da inclinação medida até o expoente 4."""
        return abs(self.expoente - EXPOENTE_TEORICO) / EXPOENTE_TEORICO * 100

    @property
    def desvio_em_sigmas(self) -> float:
        """
        Distância até 4 em barras de erro do ajuste.

        Reportado por completude, mas NÃO é o critério: o desvio observado é
        sistemático (emissividade do tungstênio), e a barra estatística é
        pequena demais para julgá-lo. Ver o cabeçalho do módulo.
        """
        if self.u_expoente <= 0:
            return float("nan")
        return abs(self.expoente - EXPOENTE_TEORICO) / self.u_expoente

    @property
    def compativel(self) -> bool:
        """A inclinação está a menos de 10% do expoente 4?"""
        return self.desvio_relativo <= TOLERANCIA_RELATIVA_PCT

    @property
    def veredicto(self) -> str:
        base = f"Inclinação {self.expoente:.2f} ± {self.u_expoente:.2f}"
        if self.compativel:
            direcao = ("ligeiramente acima de 4, como esperado para o tungstênio, "
                       "cuja emissividade cresce com a temperatura"
                       if self.expoente > EXPOENTE_TEORICO
                       else "ligeiramente abaixo de 4")
            return (f"{base} ({self.desvio_relativo:.1f}% de 4) — a lei de "
                    f"Stefan-Boltzmann se verifica; {direcao}.")
        if self.expoente < EXPOENTE_TEORICO:
            return (f"{base} ({self.desvio_relativo:.1f}% abaixo de 4) — perdas "
                    "não radiativas ainda pesam. Eleve a temperatura mínima.")
        return (f"{base} ({self.desvio_relativo:.1f}% acima de 4) — verifique a "
                "calibração das temperaturas, sobretudo R0 e os coeficientes.")


def verificar(temperatura, potencia, t_minima: float = TEMPERATURA_MINIMA_PADRAO,
              tensao=None, corrente=None,
              u_relativa_potencia: float = None) -> ResultadoStefanBoltzmann:
    """
    Ajusta log(P) × log(T) e devolve a inclinação, que deve valer ~4.

    Usa o mesmo motor de ajuste ponderado da teoria de erros, para que a
    inclinação venha com incerteza em vez de um número solto.

    A incerteza da potência sai das especificações dos instrumentos quando
    `tensao` e `corrente` são informadas — P = V·i, então as relativas somam em
    quadratura. Sem elas, usa o valor uniforme informado ou 0,1%, que é a ordem
    de grandeza medida com os specs do PWS4323.

    O corte por temperatura mínima é essencial, não cosmético: incluir os
    pontos frios enviesa a inclinação para baixo, porque lá a dissipação não é
    radiativa.
    """
    temperatura = np.asarray(temperatura, dtype=float)
    potencia = np.asarray(potencia, dtype=float)

    utilizavel = (np.isfinite(temperatura) & (temperatura > 0)
                  & np.isfinite(potencia) & (potencia > 0)
                  & (temperatura >= t_minima))

    n_total = int(temperatura.size)
    n_pontos = int(utilizavel.sum())

    if n_pontos < 3:
        raise ValueError(
            f"apenas {n_pontos} ponto(s) acima de {t_minima:.0f} K com potência "
            "positiva; são necessários ao menos 3.")

    x = np.log(temperatura[utilizavel])
    y = np.log(potencia[utilizavel])

    # d(ln P) = dP/P — a incerteza relativa da potência vira absoluta em log.
    if tensao is not None and corrente is not None:
        from utils.error_models import (PWS4323_TENSAO_READBACK,
                                        PWS4323_CORRENTE_READBACK)
        v = np.abs(np.asarray(tensao, dtype=float)[utilizavel])
        i = np.abs(np.asarray(corrente, dtype=float)[utilizavel])
        with np.errstate(divide="ignore", invalid="ignore"):
            rel_v = PWS4323_TENSAO_READBACK.incerteza_padrao(v) / v
            rel_i = PWS4323_CORRENTE_READBACK.incerteza_padrao(i) / i
        u_y = np.sqrt(rel_v ** 2 + rel_i ** 2)
        u_y = np.where(np.isfinite(u_y) & (u_y > 0), u_y, 0.001)
    else:
        u_y = np.full_like(y, u_relativa_potencia or 0.001)

    ajuste = ajuste_linear_ponderado(x, y, u_y)

    return ResultadoStefanBoltzmann(
        expoente=ajuste.m, u_expoente=ajuste.u_m, intercepto=ajuste.c,
        r2=ajuste.r2, n_pontos=n_pontos, n_total=n_total, t_minima=t_minima,
        log_temperatura=x, log_potencia=y, mascara=utilizavel,
    )
