"""Gera os artefatos que o Tableau consome: amostra em CSV e extract .hyper.

São dois produtos com papéis distintos:

  enem_amostra.csv / .hyper   → uma linha por participante (amostra). Alimenta o que
                                depende de distribuição individual: boxplot, histograma,
                                scatter. NÃO deve ser usado para ler valores exatos.
  agg_*.csv / .hyper          → tabelas já agregadas sobre a base completa. Alimentam
                                mapa, KPIs e séries, onde o número precisa estar certo.

Uso:
    python -m src.export_tableau
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config as cfg
from src.features import carregar_edicao

# Colunas exportadas na amostra. Enxugar aqui importa: cada coluna extra multiplica pelo
# número de linhas no .hyper e o Tableau Public tem limite de tamanho de workbook.
COLUNAS_AMOSTRA = [
    "ANO", "UF", "UF_NOME", "REGIAO",
    "REDE", "DEPENDENCIA_ADM_DESC", "TIPO_ESCOLA_DESC", "LOCALIZACAO_ESC_DESC",
    "SEXO_DESC", "COR_RACA_DESC", "FAIXA_ETARIA_DESC", "TREINEIRO_DESC",
    "RENDA_FAIXA", "RENDA_GRUPO", "RENDA_SM_PONTO_MEDIO",
    "ESCOLARIDADE_PAI_DESC", "ESCOLARIDADE_MAE_DESC",
    "NOTA_CN", "NOTA_CH", "NOTA_LC", "NOTA_MT", "NOTA_REDACAO",
    "NOTA_MEDIA_GERAL", "NOTA_MEDIA_OBJETIVAS", "AMPLITUDE_AREAS",
    "FAIXA_NOTA", "QUINTIL_DESEMPENHO",
    "EDICAO_COMPLETA",
]


def amostrar_edicao(df: pd.DataFrame, n_alvo: int, seed: int) -> pd.DataFrame:
    """Amostra estratificada proporcional por UF.

    Proporcional, e não com piso mínimo por estrato, de propósito: mantendo a fração de
    amostragem igual em toda UF, a amostra fica AUTOPONDERADA — qualquer média ou
    distribuição calculada sobre ela é estimador não-enviesado do total, sem precisar de
    coluna de peso. Um piso para UFs pequenas daria mais linhas a Roraima, mas
    contaminaria toda média nacional tirada da amostra, que é exatamente o erro que um
    dashboard público espalha sem ninguém perceber.

    O custo é conhecido: UFs pequenas ficam com poucas centenas de linhas. Para o número
    exato dessas UFs o dashboard usa as tabelas agregadas, calculadas sobre a base cheia.
    """
    fracao = min(n_alvo / len(df), 1.0)
    # sample(frac=...) direto no groupby aplica a fração dentro de cada UF, que é
    # exatamente a alocação proporcional desejada — e evita o apply(), que além de mais
    # lento dispara FutureWarning de coluna de agrupamento no pandas 2.x.
    return (
        df.groupby("UF", observed=True, group_keys=False)
        .sample(frac=fracao, random_state=seed)
        .reset_index(drop=True)
    )


def construir_amostra(anos=None, n_total: int = cfg.TAMANHO_AMOSTRA) -> pd.DataFrame:
    """Amostra as três edições, dividindo a cota proporcionalmente ao tamanho de cada uma."""
    anos = list(anos or cfg.ANOS)

    tamanhos = {}
    for ano in anos:
        caminho = cfg.DATA_INTERIM / f"enem_{ano}.parquet"
        tamanhos[ano] = pd.read_parquet(caminho, columns=["ANO"]).shape[0]
    total = sum(tamanhos.values())

    partes = []
    for ano in anos:
        cota = int(n_total * tamanhos[ano] / total)
        df = carregar_edicao(ano)
        amostra = amostrar_edicao(df, cota, cfg.SEED)
        print(f"  [{ano}] {len(df):>9,} → {len(amostra):>7,} linhas "
              f"({100 * len(amostra) / len(df):.2f}% da edição)")
        partes.append(amostra)
        del df

    combinada = pd.concat(partes, ignore_index=True)

    # Reindexa para o conjunto fixo de colunas: edições restritas ganham NaN nas que não
    # têm, e o .hyper sai com esquema idêntico independente de quais anos foram incluídos.
    faltantes = [c for c in COLUNAS_AMOSTRA if c not in combinada.columns]
    if faltantes:
        print(f"  colunas ausentes em todas as edições, preenchidas com nulo: {faltantes}")
    return combinada.reindex(columns=COLUNAS_AMOSTRA)


def _preparar_para_hyper(df: pd.DataFrame) -> pd.DataFrame:
    """Ajusta dtypes que o formato Hyper não aceita.

    Dois ajustes, ambos obrigatórios:

    - float32 → float64. O Hyper não tem ponto flutuante de 32 bits ("This database does
      not support 32-bit floating points") e a escrita falha inteira. Usamos float32 no
      ETL de propósito, para caber 8 milhões de linhas na memória; aqui, sobre 200 mil
      linhas de amostra, o custo de dobrar a precisão é irrelevante.
    - Categóricas ordenadas (FAIXA_NOTA, RENDA_GRUPO) e o dtype `string` do pandas viram
      texto. A ordenação categórica se perde no arquivo — por isso o TABLEAU_BLUEPRINT.md
      documenta a ordem manual de cada um desses campos, para ser refeita no Tableau.
    """
    out = df.copy()
    for col in out.columns:
        dtype = out[col].dtype
        if isinstance(dtype, pd.CategoricalDtype) or dtype == "string":
            out[col] = out[col].astype(object).where(out[col].notna(), None)
        elif dtype == "float32":
            out[col] = out[col].astype("float64")
        elif dtype == "int8" or dtype == "int16":
            out[col] = out[col].astype("int64")
    return out


def escrever_hyper(tabelas: dict[str, pd.DataFrame], destino: Path) -> bool:
    """Escreve um .hyper com uma tabela por DataFrame.

    Devolve False (sem levantar exceção) se o Hyper API não estiver disponível: o
    tableauhyperapi só tem binário para algumas plataformas, e a ausência dele não pode
    derrubar um pipeline cujo entregável principal — o CSV — já está pronto. Quem chama
    avisa o usuário.
    """
    try:
        import pantab
    except ImportError as exc:
        print(f"\n  ⚠  .hyper NÃO gerado: {exc}")
        print("     O CSV foi gerado normalmente e o Tableau lê CSV sem problema.")
        return False

    try:
        pantab.frames_to_hyper(
            {nome: _preparar_para_hyper(df) for nome, df in tabelas.items()},
            destino,
        )
    except Exception as exc:  # noqa: BLE001 — queremos degradar para CSV, não quebrar
        print(f"\n  ⚠  .hyper NÃO gerado — falha ao escrever: {type(exc).__name__}: {exc}")
        print("     O CSV foi gerado normalmente e o Tableau lê CSV sem problema.")
        return False

    print(f"  .hyper  {destino.name} ({destino.stat().st_size / 1e6:.1f} MB) "
          f"— tabelas: {', '.join(tabelas)}")
    return True


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--anos", nargs="+", type=int, default=list(cfg.ANOS))
    ap.add_argument("--n", type=int, default=cfg.TAMANHO_AMOSTRA)
    args = ap.parse_args()

    print("Construindo amostra estratificada por UF...")
    amostra = construir_amostra(args.anos, args.n)

    csv_amostra = cfg.OUTPUTS_TABLEAU / "enem_amostra.csv"
    amostra.to_csv(csv_amostra, index=False, encoding="utf-8", float_format="%.2f")
    print(f"\n  CSV     {csv_amostra.name} "
          f"({len(amostra):,} linhas, {csv_amostra.stat().st_size / 1e6:.1f} MB)")

    # As tabelas agregadas já foram geradas por src/aggregate.py; aqui só as recolhemos
    # para dentro do mesmo .hyper, de modo que o Tableau precise de um arquivo só.
    tabelas = {"amostra": amostra}
    for caminho in sorted(cfg.DATA_PROCESSED.glob("agg_*.csv")):
        tabelas[caminho.stem] = pd.read_csv(caminho)
        destino = cfg.OUTPUTS_TABLEAU / caminho.name
        if caminho.resolve() != destino.resolve():
            destino.write_bytes(caminho.read_bytes())

    if "agg_uf" not in tabelas:
        print("  ⚠  tabelas agregadas não encontradas — rode `python -m src.aggregate` antes.")
    else:
        print(f"  CSV     {len(tabelas) - 1} tabelas agregadas copiadas para outputs/tableau/")

    escrever_hyper(tabelas, cfg.OUTPUTS_TABLEAU / "enem_tableau.hyper")

    print(f"\nArtefatos em {cfg.OUTPUTS_TABLEAU}")


if __name__ == "__main__":
    main()
