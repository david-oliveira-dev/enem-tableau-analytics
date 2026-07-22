"""Feature engineering: decodifica códigos do INEP e cria as variáveis de análise.

Entrada: Parquet harmonizado do ETL (nomes canônicos, códigos numéricos crus).
Saída: DataFrame com colunas legíveis, prontas para virar dimensão no Tableau.

A regra que orienta tudo aqui: o Tableau é ótimo em agregar e péssimo em decodificar.
Toda tradução de código para rótulo, todo agrupamento de faixa e toda ordenação
categórica são resolvidos em Python — o Tableau recebe texto legível e já ordenado, e
o campo calculado lá dentro fica reservado para o que é genuinamente de visualização.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config as cfg


def _categoria_ordenada(serie: pd.Series, ordem: list[str]) -> pd.Series:
    """Categórica ordenada, ignorando categorias que não aparecem nos dados."""
    presentes = [c for c in ordem if c in set(serie.dropna().unique())]
    return pd.Categorical(serie, categories=presentes, ordered=True)


def adicionar_notas_agregadas(df: pd.DataFrame) -> pd.DataFrame:
    """Médias por participante.

    Duas médias, de propósito:

    - NOTA_MEDIA_OBJETIVAS: média das 4 provas de múltipla escolha. É a métrica
      comparável entre participantes, porque todas usam TRI na mesma escala.
    - NOTA_MEDIA_GERAL: média simples das 5 notas, incluindo Redação. É a métrica que o
      público reconhece como "a nota do ENEM", e a que aparece no dashboard.

    Nenhuma das duas é a nota de corte real de nenhum programa: SISU, ProUni e FIES
    aplicam pesos por curso que variam caso a caso. Média simples é escolha analítica
    explícita, não tentativa de reproduzir o cálculo oficial.
    """
    objetivas = ["NOTA_CN", "NOTA_CH", "NOTA_LC", "NOTA_MT"]
    todas = objetivas + ["NOTA_REDACAO"]

    df["NOTA_MEDIA_OBJETIVAS"] = df[objetivas].mean(axis=1).round(2)
    df["NOTA_MEDIA_GERAL"] = df[todas].mean(axis=1).round(2)

    # Amplitude entre a melhor e a pior área do participante: mede o quanto o desempenho
    # é irregular. Serve para separar quem tem base ampla de quem carrega a média numa
    # área só — recorte que não existe pronto em lugar nenhum do dataset.
    df["AMPLITUDE_AREAS"] = (df[todas].max(axis=1) - df[todas].min(axis=1)).round(2)

    return df


def adicionar_faixas_desempenho(df: pd.DataFrame) -> pd.DataFrame:
    """Faixas de desempenho por quintil e por corte absoluto.

    Duas lógicas diferentes, porque respondem a perguntas diferentes:

    - QUINTIL_DESEMPENHO é RELATIVO e calculado DENTRO de cada edição. Divide os
      participantes daquele ano em cinco grupos iguais. Como é recalculado por ano, ele
      nunca mede evolução — 20% da base sempre cai no quintil superior, por construção.
      Serve para comparar grupos DENTRO do mesmo ano ("qual a chance de um aluno de
      escola pública chegar ao quintil superior?").

    - FAIXA_NOTA é ABSOLUTA, em cortes fixos de 100 pontos na escala TRI. Como o corte
      não muda entre edições, é ela que permite comparar 2022, 2023 e 2024.

    Trocar uma pela outra na hora errada é o erro sutil mais provável nesta análise, daí
    os nomes serem explicitamente diferentes.
    """
    # qcut sobre a nota crua quebra quando há notas empatadas suficientes para dois
    # cortes caírem no mesmo valor: com duplicates="drop" sobram menos faixas que
    # rótulos e o pandas levanta ValueError. Aplicar qcut sobre o RANK (com desempate
    # por ordem de ocorrência) torna todos os valores únicos, garantindo sempre 5
    # faixas de tamanho igual — que é a definição de quintil que queremos.
    rotulos = ["Q1 (mais baixo)", "Q2", "Q3", "Q4", "Q5 (mais alto)"]
    df["QUINTIL_DESEMPENHO"] = (
        df.groupby("ANO", observed=True)["NOTA_MEDIA_GERAL"]
        .transform(lambda s: pd.qcut(s.rank(method="first"), 5, labels=rotulos))
    )

    cortes = [0, 400, 500, 600, 700, 1000]
    rotulos = ["Até 400", "400 a 500", "500 a 600", "600 a 700", "Acima de 700"]
    df["FAIXA_NOTA"] = pd.cut(df["NOTA_MEDIA_GERAL"], bins=cortes, labels=rotulos,
                              include_lowest=True)

    return df


def adicionar_recortes_geograficos(df: pd.DataFrame) -> pd.DataFrame:
    """UF por extenso e região — a hierarquia geográfica do dashboard."""
    uf = df["UF_PROVA"].astype("string")
    df["UF"] = uf
    df["UF_NOME"] = uf.map(cfg.UF_NOME)
    df["REGIAO"] = uf.map(cfg.UF_REGIAO)
    return df


def adicionar_recortes_escola(df: pd.DataFrame) -> pd.DataFrame:
    """Recortes de escola — o ponto onde as três edições divergem.

    REDE (Pública/Privada) sai de DEPENDENCIA_ADM, que vem do pareamento com o Censo
    Escolar e existe nas três edições. É o recorte comparável ao longo do tempo.

    TIPO_ESCOLA_DESC é autodeclarado no questionário e só existe até 2023. Cobre um
    conjunto diferente de participantes e traz a categoria "Não informado", que é a
    maioria da base (quem já concluiu o EM costuma não responder). Tratamos essa
    categoria como classe própria, e NÃO como valor ausente a imputar: a ausência de
    resposta aqui é informativa (correlaciona com já ter concluído o EM), então imputar
    ou descartar distorceria o recorte.
    """
    if "DEPENDENCIA_ADM" in df.columns:
        dep = df["DEPENDENCIA_ADM"].map(cfg.MAP_DEPENDENCIA)
        df["DEPENDENCIA_ADM_DESC"] = dep
        df["REDE"] = dep.map(cfg.MAP_REDE)

    if "TIPO_ESCOLA" in df.columns:
        df["TIPO_ESCOLA_DESC"] = df["TIPO_ESCOLA"].map(cfg.MAP_ESCOLA)

    if "LOCALIZACAO_ESC" in df.columns:
        df["LOCALIZACAO_ESC_DESC"] = df["LOCALIZACAO_ESC"].map(cfg.MAP_LOCALIZACAO_ESC)

    return df


def adicionar_recortes_socioeconomicos(df: pd.DataFrame) -> pd.DataFrame:
    """Renda, sexo, cor/raça, escolaridade dos pais.

    Só se aplica às edições completas (até 2023). Em 2024 essas colunas não existem no
    lado dos resultados, então as funções abaixo simplesmente não encontram o que mapear
    e o DataFrame sai sem elas — o notebook checa a presença antes de plotar.
    """
    if "RENDA_FAMILIAR" in df.columns:
        renda = df["RENDA_FAMILIAR"].astype("string")
        df["RENDA_FAIXA"] = renda.map(cfg.MAP_RENDA_SM)
        df["RENDA_GRUPO"] = _categoria_ordenada(
            renda.map(cfg.MAP_RENDA_GRUPO), cfg.ORDEM_RENDA_GRUPO)
        # Versão numérica: ponto médio da faixa em salários mínimos. Necessária para
        # correlação e para o scatter renda x nota, onde um eixo categórico não permitiria
        # linha de tendência. Usar múltiplos de SM (e não reais) mantém as três edições
        # comparáveis apesar do reajuste anual do salário mínimo.
        df["RENDA_SM_PONTO_MEDIO"] = renda.map(cfg.RENDA_PONTO_MEDIO_SM).astype("float32")

    if "SEXO" in df.columns:
        df["SEXO_DESC"] = df["SEXO"].astype("string").map(cfg.MAP_SEXO)

    if "COR_RACA" in df.columns:
        df["COR_RACA_DESC"] = df["COR_RACA"].map(cfg.MAP_COR_RACA)

    if "FAIXA_ETARIA" in df.columns:
        df["FAIXA_ETARIA_DESC"] = df["FAIXA_ETARIA"].map(cfg.MAP_FAIXA_ETARIA)

    for origem, destino in [("ESCOLARIDADE_PAI", "ESCOLARIDADE_PAI_DESC"),
                            ("ESCOLARIDADE_MAE", "ESCOLARIDADE_MAE_DESC")]:
        if origem in df.columns:
            df[destino] = df[origem].astype("string").map(cfg.MAP_ESCOLARIDADE_PAIS)

    if "TREINEIRO" in df.columns:
        df["TREINEIRO_DESC"] = df["TREINEIRO"].map({0: "Não", 1: "Sim"})

    return df


def construir_features(df: pd.DataFrame) -> pd.DataFrame:
    """Aplica a cadeia completa de feature engineering."""
    df = adicionar_notas_agregadas(df)
    df = adicionar_faixas_desempenho(df)
    df = adicionar_recortes_geograficos(df)
    df = adicionar_recortes_escola(df)
    df = adicionar_recortes_socioeconomicos(df)
    return df


def carregar_edicao(ano: int, com_features: bool = True) -> pd.DataFrame:
    """Lê o Parquet de uma edição e opcionalmente aplica as features."""
    caminho = cfg.DATA_INTERIM / f"enem_{ano}.parquet"
    if not caminho.exists():
        raise FileNotFoundError(f"{caminho} não existe. Rode: python -m src.etl --anos {ano}")
    df = pd.read_parquet(caminho)
    return construir_features(df) if com_features else df


def carregar_todas(anos=None, com_features: bool = True) -> pd.DataFrame:
    """Empilha as edições numa base única.

    As edições têm conjuntos de colunas diferentes (2024 não tem renda, sexo etc.).
    O concat preenche as faltantes com NaN, e a coluna EDICAO_COMPLETA marca quais
    linhas podem ser usadas em recorte socioeconômico — filtrar por ela é mais honesto
    do que filtrar por ano, porque o motivo fica explícito na leitura do código.
    """
    anos = anos or cfg.ANOS
    partes = [carregar_edicao(ano, com_features=com_features) for ano in anos]
    return pd.concat(partes, ignore_index=True)


def formato_longo_areas(df: pd.DataFrame) -> pd.DataFrame:
    """Converte as 5 notas de colunas para linhas (formato longo).

    O Tableau agrega muito melhor em formato longo: com uma coluna AREA e uma coluna
    NOTA, o gráfico de barras por área de conhecimento vira um único campo no eixo,
    em vez de cinco medidas separadas que não dá para ordenar nem filtrar juntas.
    """
    dimensoes = [c for c in [
        "ANO", "UF", "UF_NOME", "REGIAO", "REDE", "DEPENDENCIA_ADM_DESC",
        "TIPO_ESCOLA_DESC", "SEXO_DESC", "COR_RACA_DESC", "RENDA_GRUPO",
        "FAIXA_ETARIA_DESC", "QUINTIL_DESEMPENHO",
    ] if c in df.columns]

    notas = [c for c in cfg.CANONICAS_NOTA if c in df.columns]
    longo = df[dimensoes + notas].melt(
        id_vars=dimensoes, value_vars=notas, var_name="AREA_COD", value_name="NOTA")
    longo["AREA"] = longo["AREA_COD"].map(cfg.AREAS)
    return longo.drop(columns="AREA_COD").dropna(subset=["NOTA"])
