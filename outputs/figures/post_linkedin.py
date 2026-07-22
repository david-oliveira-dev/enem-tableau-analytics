"""Gera a imagem do post de LinkedIn (1200x1200) a partir das tabelas agregadas.

Forma escolhida: dumbbell (halteres). O dado é uma comparação pareada — duas redes
sobre as mesmas cinco áreas — e o que interessa é o TAMANHO DA DISTÂNCIA entre os
pontos, não o valor absoluto de cada um. Barras agrupadas mostrariam os dez valores e
esconderiam justamente a distância; o dumbbell desenha a distância como objeto visual.

Paleta: slots categóricos 1 e 2 da paleta de referência, validados nos seis checks
(CVD ΔE 24,7 em protanopia; contraste ≥ 3:1 sobre a superfície).
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.patches import FancyBboxPatch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src import config as cfg

SUPERFICIE = "#fcfcfb"
TINTA = "#0b0b0b"
TINTA_2 = "#52514e"
MUDO = "#898781"
PUBLICA = "#2a78d6"
PRIVADA = "#eb6834"
TRILHO = "#dcdcd6"

ANO = 2023


def dados() -> pd.DataFrame:
    area = pd.read_csv(cfg.DATA_PROCESSED / "agg_area.csv")
    a = area[(area.ANO == ANO) & area.REDE.notna()]
    # Média ponderada pelo nº de participantes: as UFs têm tamanhos muito diferentes.
    nac = (a.assign(soma=a.nota_media * a.n_participantes)
             .groupby(["AREA", "REDE"])
             .apply(lambda g: g.soma.sum() / g.n_participantes.sum(), include_groups=False)
             .unstack())
    nac["gap"] = nac["Privada"] - nac["Pública"]
    return nac.sort_values("gap")


def construir() -> Path:
    df = dados()

    fig = plt.figure(figsize=(12, 12), dpi=100)
    fig.patch.set_facecolor(SUPERFICIE)

    # ---------------------------------------------------------------- cabeçalho
    fig.text(0.06, 0.965, "Onde a desigualdade do ENEM se concentra",
             fontsize=29, weight="bold", color=TINTA, va="top")
    fig.text(0.06, 0.912,
             "A diferença entre escola privada e pública não é a mesma em todas as áreas.\n"
             "Em Redação ela é mais que o triplo da de Linguagens.",
             fontsize=16.5, color=TINTA_2, va="top", linespacing=1.5)

    # ---------------------------------------------------------------- dumbbell
    # left=0.25 reserva espaço para rótulos longos ("Linguagens e Códigos"); com margem
    # menor eles saem da imagem, porque salvamos sem bbox_inches="tight" para manter o
    # quadrado exato de 1200x1200 que o LinkedIn espera.
    ax = fig.add_axes([0.25, 0.315, 0.69, 0.46])
    ax.set_facecolor(SUPERFICIE)
    y = range(len(df))

    for i, (nome, row) in enumerate(df.iterrows()):
        # Trilho por trás dos dois pontos: é ele que materializa a distância.
        ax.plot([row["Pública"], row["Privada"]], [i, i],
                color=TRILHO, lw=7, solid_capstyle="round", zorder=1)
        # Anel de 2px na cor da superfície para separar marcas que se aproximam.
        ax.scatter(row["Pública"], i, s=430, color=PUBLICA, zorder=3,
                   edgecolors=SUPERFICIE, linewidths=2)
        ax.scatter(row["Privada"], i, s=430, color=PRIVADA, zorder=3,
                   edgecolors=SUPERFICIE, linewidths=2)

        # Rótulo direto do gap, acima do trilho. Duas séries, ambas rotuladas —
        # identidade nunca depende só da cor.
        meio = (row["Pública"] + row["Privada"]) / 2
        ax.annotate(f"+{row['gap']:.0f} pts", (meio, i), xytext=(0, 26),
                    textcoords="offset points", ha="center",
                    fontsize=16.5, weight="bold", color=TINTA)
        ax.annotate(f"{row['Pública']:.0f}", (row["Pública"], i), xytext=(-17, -6),
                    textcoords="offset points", ha="right", fontsize=14, color=TINTA_2)
        ax.annotate(f"{row['Privada']:.0f}", (row["Privada"], i), xytext=(17, -6),
                    textcoords="offset points", ha="left", fontsize=14, color=TINTA_2)

    ax.set_yticks(list(y))
    ax.set_yticklabels(df.index, fontsize=17, color=TINTA)
    ax.set_xlim(425, 845)
    ax.set_ylim(-0.7, len(df) - 0.3)
    ax.set_xlabel("Nota média — ENEM 2023", fontsize=14, color=MUDO, labelpad=14)
    ax.tick_params(axis="x", colors=MUDO, labelsize=13)
    ax.tick_params(axis="y", length=0)
    ax.grid(axis="x", color="#ececE6", lw=1)
    ax.set_axisbelow(True)
    for lado in ("top", "right", "left"):
        ax.spines[lado].set_visible(False)
    ax.spines["bottom"].set_color("#e4e4de")

    # Legenda sempre presente com duas séries, numa faixa própria acima do gráfico
    # para não disputar espaço com as marcas nem com o subtítulo.
    ax.scatter([], [], s=250, color=PUBLICA, label="Escola pública")
    ax.scatter([], [], s=250, color=PRIVADA, label="Escola privada")
    ax.legend(loc="lower left", frameon=False, fontsize=15.5, ncol=2,
              handletextpad=0.5, columnspacing=2.2, bbox_to_anchor=(0.0, 1.035))

    # ---------------------------------------------------------------- destaque
    caixa = FancyBboxPatch((0.06, 0.125), 0.88, 0.125, transform=fig.transFigure,
                           boxstyle="round,pad=0.010,rounding_size=0.012",
                           facecolor="#f2f1ec", edgecolor="none", zorder=0)
    fig.patches.append(caixa)

    fig.text(0.105, 0.1875, "4,2×", fontsize=42, weight="bold", color=PRIVADA,
             va="center", ha="left")
    fig.text(0.245, 0.1875,
             "é a chance a mais que um aluno de escola privada tem\n"
             "de chegar ao quintil superior: 50,5% contra 12,1%.",
             fontsize=16.5, color=TINTA, va="center", linespacing=1.7)

    # ---------------------------------------------------------------- rodapé
    fig.text(0.06, 0.075,
             "Microdados do ENEM 2023 (INEP) · 2,7 milhões de participantes presentes nos dois dias\n"
             "Rede de ensino a partir do pareamento com o Censo Escolar (cobre 26,9% dos participantes)",
             fontsize=12.5, color=MUDO, va="top", linespacing=1.7)

    destino = cfg.OUTPUTS_FIGURES / "post_linkedin.png"
    fig.savefig(destino, facecolor=SUPERFICIE, bbox_inches=None)
    plt.close(fig)
    return destino


if __name__ == "__main__":
    print(construir())
