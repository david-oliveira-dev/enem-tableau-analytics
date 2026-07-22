"""Tabelas agregadas calculadas sobre a base COMPLETA.

Por que existir, se já vamos entregar uma amostra?

A amostra de 200 mil linhas serve para o Tableau desenhar distribuições (histograma,
boxplot, scatter) sem engasgar. Mas se o mapa coroplético e os KPIs também saíssem da
amostra, os números exibidos seriam estimativas com erro amostral — e um dashboard que
mostra "média de Roraima: 512,3" com uma casa decimal está afirmando precisão que a
amostra não tem.

Então dividimos: as tabelas daqui são calculadas sobre TODOS os ~7 milhões de
participantes das três edições e alimentam mapa, KPIs e séries. A amostra alimenta só o
que precisa de distribuição individual. É a razão de o dashboard ter duas fontes.

Uso:
    python -m src.aggregate
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config as cfg
from src.features import carregar_edicao

# Métricas repetidas em toda tabela agregada. n_participantes acompanha sempre a média:
# sem ele não dá para saber se uma diferença de 30 pontos vem de 50 mil pessoas ou de 12.
AGG_NOTAS = {
    "nota_media_geral": ("NOTA_MEDIA_GERAL", "mean"),
    "nota_mediana_geral": ("NOTA_MEDIA_GERAL", "median"),
    "nota_desvio_padrao": ("NOTA_MEDIA_GERAL", "std"),
    "nota_media_objetivas": ("NOTA_MEDIA_OBJETIVAS", "mean"),
    "nota_media_cn": ("NOTA_CN", "mean"),
    "nota_media_ch": ("NOTA_CH", "mean"),
    "nota_media_lc": ("NOTA_LC", "mean"),
    "nota_media_mt": ("NOTA_MT", "mean"),
    "nota_media_redacao": ("NOTA_REDACAO", "mean"),
    "n_participantes": ("NOTA_MEDIA_GERAL", "size"),
}

# Abaixo deste número de participantes, a média de um grupo é instável e pode expor
# indivíduos (ex.: 3 alunos de escola federal numa UF pequena). Suprimimos a linha em vez
# de publicá-la — mesma lógica que o INEP aplica ao mascarar códigos de escola.
N_MINIMO_GRUPO = 30


def _agregar(df: pd.DataFrame, chaves: list[str]) -> pd.DataFrame:
    """Agrega por um conjunto de chaves, arredonda e suprime grupos pequenos."""
    chaves = [c for c in chaves if c in df.columns]
    out = (
        df.groupby(chaves, observed=True)
        .agg(**AGG_NOTAS)
        .reset_index()
    )
    out = out[out["n_participantes"] >= N_MINIMO_GRUPO]

    for col in out.columns:
        if col.startswith("nota_"):
            out[col] = out[col].round(2)

    return out.sort_values(chaves).reset_index(drop=True)


def por_uf(df: pd.DataFrame) -> pd.DataFrame:
    """Alimenta o mapa coroplético. Uma linha por UF por edição."""
    out = _agregar(df, ["ANO", "UF", "UF_NOME", "REGIAO"])

    # Diferença para a média nacional daquele ano: é o que dá cor ao mapa divergente.
    # Calcular aqui, e não no Tableau, evita que o valor mude conforme o filtro aplicado
    # — o desvio precisa ser sempre em relação ao Brasil, não à seleção corrente.
    media_nacional = df.groupby("ANO", observed=True)["NOTA_MEDIA_GERAL"].mean()
    out["media_nacional"] = out["ANO"].map(media_nacional).round(2)
    out["desvio_vs_nacional"] = (out["nota_media_geral"] - out["media_nacional"]).round(2)

    return out


def por_uf_rede(df: pd.DataFrame) -> pd.DataFrame:
    """Nota por UF e rede de ensino — comparável nas três edições."""
    return _agregar(df.dropna(subset=["REDE"]), ["ANO", "UF", "REGIAO", "REDE"])


def por_rede(df: pd.DataFrame) -> pd.DataFrame:
    """Série temporal do gap público x privado."""
    return _agregar(df.dropna(subset=["REDE"]), ["ANO", "REDE"])


def _exige(df: pd.DataFrame, *colunas: str) -> bool:
    """True se a edição tem todas as colunas pedidas.

    Numa edição restrita (2024) as colunas socioeconômicas simplesmente não existem —
    checar presença é mais direto do que checar o ano, e continua correto se o INEP
    mudar o esquema outra vez.
    """
    return all(c in df.columns for c in colunas)


def por_renda(df: pd.DataFrame) -> pd.DataFrame:
    """Gradiente de renda. Só edições completas (2024 não liga renda a nota)."""
    if not _exige(df, "RENDA_GRUPO", "RENDA_SM_PONTO_MEDIO"):
        return pd.DataFrame()
    df = df[df["EDICAO_COMPLETA"] & df["RENDA_GRUPO"].notna()]
    if df.empty:
        return pd.DataFrame()
    out = _agregar(df, ["ANO", "RENDA_GRUPO"])
    # Ponto médio em salários mínimos por grupo: dá ao Tableau um eixo X numérico para
    # o scatter e para a linha de tendência.
    medio = df.groupby("RENDA_GRUPO", observed=True)["RENDA_SM_PONTO_MEDIO"].mean()
    out["renda_sm_ponto_medio"] = out["RENDA_GRUPO"].map(medio).round(2)
    return out


def por_renda_rede(df: pd.DataFrame) -> pd.DataFrame:
    """Cruzamento renda x rede — separa efeito de renda de efeito de escola."""
    if not _exige(df, "RENDA_GRUPO", "REDE"):
        return pd.DataFrame()
    df = df[df["EDICAO_COMPLETA"] & df["RENDA_GRUPO"].notna() & df["REDE"].notna()]
    return _agregar(df, ["ANO", "RENDA_GRUPO", "REDE"]) if not df.empty else pd.DataFrame()


def por_perfil(df: pd.DataFrame) -> pd.DataFrame:
    """Sexo e cor/raça. Só edições completas."""
    if not _exige(df, "SEXO_DESC", "COR_RACA_DESC"):
        return pd.DataFrame()
    df = df[df["EDICAO_COMPLETA"]]
    return _agregar(df, ["ANO", "SEXO_DESC", "COR_RACA_DESC"]) if not df.empty else pd.DataFrame()


def por_area(df: pd.DataFrame) -> pd.DataFrame:
    """Formato longo: uma linha por (edição, UF, rede, área de conhecimento).

    É a tabela que alimenta o gráfico de barras por área. Construída direto na agregação
    em vez de derreter a base inteira — derreter 7 milhões de linhas por 5 áreas geraria
    35 milhões de linhas para depois agregar, o que é desperdício puro.
    """
    linhas = []
    chaves = [c for c in ["ANO", "UF", "REGIAO", "REDE"] if c in df.columns]
    for coluna, area in cfg.AREAS.items():
        if coluna not in df.columns:
            continue
        parte = (
            df.groupby(chaves, observed=True)[coluna]
            .agg(nota_media="mean", nota_mediana="median", n_participantes="size")
            .reset_index()
        )
        parte["AREA"] = area
        linhas.append(parte)

    out = pd.concat(linhas, ignore_index=True)
    out = out[out["n_participantes"] >= N_MINIMO_GRUPO]
    out["nota_media"] = out["nota_media"].round(2)
    out["nota_mediana"] = out["nota_mediana"].round(2)
    return out.sort_values(chaves + ["AREA"]).reset_index(drop=True)


def distribuicao_faixas(df: pd.DataFrame) -> pd.DataFrame:
    """Percentual de participantes em cada faixa absoluta de nota, por UF e rede.

    Usa FAIXA_NOTA (corte fixo), não quintil — só assim a comparação entre edições
    significa alguma coisa. Ver docstring de features.adicionar_faixas_desempenho.
    """
    chaves = [c for c in ["ANO", "UF", "REDE"] if c in df.columns]
    out = (
        df.dropna(subset=["FAIXA_NOTA"])
        .groupby(chaves + ["FAIXA_NOTA"], observed=True)
        .size().rename("n_participantes").reset_index()
    )
    total = out.groupby(chaves, observed=True)["n_participantes"].transform("sum")
    out["pct_participantes"] = (100 * out["n_participantes"] / total).round(2)
    return out[out.groupby(chaves, observed=True)["n_participantes"].transform("sum")
               >= N_MINIMO_GRUPO].reset_index(drop=True)


TABELAS = {
    "agg_uf": por_uf,
    "agg_uf_rede": por_uf_rede,
    "agg_rede": por_rede,
    "agg_renda": por_renda,
    "agg_renda_rede": por_renda_rede,
    "agg_perfil": por_perfil,
    "agg_area": por_area,
    "agg_faixas": distribuicao_faixas,
}


def gerar_todas(anos=None) -> dict[str, pd.DataFrame]:
    """Roda todas as agregações uma edição por vez e empilha os resultados.

    Processar edição a edição em vez de carregar as três juntas mantém o pico de memória
    em ~1 edição, o que importa numa máquina com HD mecânico: estourar para swap aqui
    custaria minutos, não segundos.
    """
    anos = anos or cfg.ANOS
    acumulado: dict[str, list[pd.DataFrame]] = {nome: [] for nome in TABELAS}

    for ano in anos:
        print(f"[agregação] carregando edição {ano}...")
        df = carregar_edicao(ano)
        for nome, funcao in TABELAS.items():
            resultado = funcao(df)
            if not resultado.empty:
                acumulado[nome].append(resultado)
        del df

    saida = {}
    for nome, partes in acumulado.items():
        if not partes:
            print(f"  [agregação] {nome}: vazia (nenhuma edição elegível), pulando.")
            continue
        saida[nome] = pd.concat(partes, ignore_index=True)
    return saida


def main() -> None:
    tabelas = gerar_todas()
    for nome, df in tabelas.items():
        destino = cfg.DATA_PROCESSED / f"{nome}.csv"
        df.to_csv(destino, index=False, encoding="utf-8", float_format="%.2f")
        print(f"  {nome:16} {len(df):>7,} linhas  →  {destino.name}")


if __name__ == "__main__":
    main()
