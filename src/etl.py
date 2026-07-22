"""ETL dos microdados do ENEM: leitura em blocos, limpeza e harmonização entre edições.

O CSV de uma edição tem ~1,6 GB e 76 colunas. Ler isso de uma vez num notebook é receita
para travar a máquina, então tudo aqui é feito em blocos (`chunksize`), mantendo em
memória apenas as colunas de interesse já filtradas.

Saída: um Parquet por edição em data/interim/, com nomes de coluna CANÔNICOS —
comparável entre 2022, 2023 e 2024 apesar das mudanças de esquema do INEP.

Uso:
    python -m src.etl --anos 2022 2023 2024
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config as cfg


def _colunas_para_ler(esquema: cfg.EsquemaEdicao, header: list[str]) -> dict[str, str]:
    """Interseção entre o que queremos e o que o arquivo realmente tem.

    Devolve {nome_cru: nome_canonico}. Falha alto se faltar coluna essencial: melhor
    quebrar aqui do que produzir um Parquet silenciosamente incompleto.
    """
    presentes, ausentes = {}, []
    for canonico, cru in esquema.colunas.items():
        if cru in header:
            presentes[cru] = canonico
        else:
            ausentes.append(f"{canonico} ({cru})")

    essenciais = set(cfg.CANONICAS_NOTA) | set(cfg.CANONICAS_PRESENCA) | {"UF_PROVA", "ANO"}
    faltando_essencial = essenciais - set(presentes.values())
    if faltando_essencial:
        raise KeyError(
            f"Edição {esquema.ano}: colunas essenciais ausentes no CSV: "
            f"{sorted(faltando_essencial)}. O INEP pode ter mudado o esquema de novo — "
            f"confira o dicionário do pacote e atualize ESQUEMAS em src/config.py."
        )
    if ausentes:
        print(f"  [{esquema.ano}] colunas opcionais ausentes: {', '.join(ausentes)}")
    return presentes


def _limpar_bloco(df: pd.DataFrame) -> pd.DataFrame:
    """Regras de limpeza aplicadas bloco a bloco.

    DECISÃO CENTRAL — quem entra na análise:
    Mantemos só quem esteve presente nos DOIS dias de prova (TP_PRESENCA == 1 nas quatro
    áreas). Faltantes e eliminados aparecem no CSV com nota vazia, e incluí-los como zero
    seria o erro clássico deste dataset: derrubaria a média de toda UF proporcionalmente à
    taxa de abstenção, transformando "onde as pessoas faltam mais" em "onde as pessoas vão
    pior". Como a abstenção do ENEM passa de 25%, o viés não seria pequeno.

    Ausência de nota após esse filtro é resíduo (ex.: redação anulada), e aí sim vira NaN
    — que o pandas ignora nas médias, em vez de puxá-las para baixo.
    """
    # 1 = Presente. 0 = Faltou, 2 = Eliminado.
    presenca = [c for c in cfg.CANONICAS_PRESENCA if c in df.columns]
    mask = pd.Series(True, index=df.index)
    for col in presenca:
        mask &= df[col] == 1
    df = df[mask]

    # Nota 0 nas objetivas é impossível na TRI (a escala parte de ~300 para quem acerta
    # zero itens); quando aparece, é registro defeituoso. Na redação, porém, 0 é nota
    # legítima (fuga ao tema, anulada) e deve ser preservada.
    for col in ["NOTA_CN", "NOTA_CH", "NOTA_LC", "NOTA_MT"]:
        if col in df.columns:
            df.loc[df[col] <= 0, col] = pd.NA

    # Descarta quem ficou sem nenhuma nota objetiva utilizável.
    objetivas = [c for c in ["NOTA_CN", "NOTA_CH", "NOTA_LC", "NOTA_MT"] if c in df.columns]
    if objetivas:
        df = df[df[objetivas].notna().any(axis=1)]

    # UF é a espinha dorsal do mapa coroplético; linha sem UF não serve para nada.
    if "UF_PROVA" in df.columns:
        df = df[df["UF_PROVA"].notna()]

    return df


def processar_edicao(ano: int, limite_blocos: int | None = None) -> Path:
    """Lê o CSV bruto de uma edição e grava o Parquet harmonizado."""
    esquema = cfg.ESQUEMAS.get(ano)
    if esquema is None:
        raise KeyError(
            f"Sem mapa de esquema para {ano}. Adicione uma entrada em ESQUEMAS "
            f"(src/config.py) depois de conferir o dicionário do INEP daquela edição."
        )

    origem = cfg.DATA_INTERIM / f"MICRODADOS_ENEM_{ano}.csv"
    if not origem.exists():
        raise FileNotFoundError(
            f"{origem} não existe. Rode: python src/download.py --anos {ano} --extrair"
        )

    destino = cfg.DATA_INTERIM / f"enem_{ano}.parquet"

    print(f"\n[{ano}] processando {origem.name} ({origem.stat().st_size / 1e9:.1f} GB)")
    if not esquema.completo:
        print(f"  [{ano}] ATENÇÃO — edição restrita: {esquema.observacao}")

    header = pd.read_csv(origem, sep=";", encoding="latin-1", nrows=0).columns.tolist()
    mapa = _colunas_para_ler(esquema, header)
    dtypes = {cru: cfg.DTYPES_CANONICOS[can] for cru, can in mapa.items()
              if cfg.DTYPES_CANONICOS.get(can) not in (None, "int8", "int16")}
    # int8/int16 ficam de fora do dtype de leitura: se a coluna tiver qualquer vazio, o
    # pandas estoura ao converter. Convertemos depois, com segurança, no downcast.

    blocos, total_lido, total_mantido = [], 0, 0
    inicio = time.time()

    leitor = pd.read_csv(
        origem,
        sep=";",
        encoding="latin-1",
        usecols=list(mapa),
        dtype=dtypes,
        chunksize=cfg.CHUNKSIZE,
        low_memory=False,
    )

    for i, bloco in enumerate(leitor):
        if limite_blocos is not None and i >= limite_blocos:
            break
        total_lido += len(bloco)
        bloco = bloco.rename(columns=mapa)
        bloco = _limpar_bloco(bloco)
        total_mantido += len(bloco)
        blocos.append(bloco)
        if i % 5 == 0:
            print(f"  [{ano}] bloco {i:>3} | lidos {total_lido:>9,} | "
                  f"mantidos {total_mantido:>9,}", flush=True)

    df = pd.concat(blocos, ignore_index=True)
    del blocos

    # Downcast só agora, quando não há mais concatenação pela frente (concat de
    # categóricas com categorias diferentes por bloco volta para object).
    for canonico, tipo in cfg.DTYPES_CANONICOS.items():
        if canonico in df.columns and tipo in ("int8", "int16"):
            df[canonico] = pd.to_numeric(df[canonico], errors="coerce").astype("float32")

    # ANO nem sempre vem preenchido de forma confiável; fixamos pela edição processada.
    df["ANO"] = ano
    df["EDICAO_COMPLETA"] = esquema.completo

    df.to_parquet(destino, index=False, compression="snappy")

    taxa = 100 * total_mantido / total_lido if total_lido else 0
    print(f"  [{ano}] {total_lido:,} lidos → {total_mantido:,} mantidos ({taxa:.1f}%) "
          f"em {(time.time() - inicio) / 60:.1f} min")
    print(f"  [{ano}] {len(df.columns)} colunas → {destino} "
          f"({destino.stat().st_size / 1e6:.0f} MB)")
    return destino


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--anos", nargs="+", type=int, default=list(cfg.ANOS))
    ap.add_argument("--limite-blocos", type=int, default=None,
                    help="processa só os N primeiros blocos (para testar rápido)")
    args = ap.parse_args()

    for ano in args.anos:
        processar_edicao(ano, limite_blocos=args.limite_blocos)


if __name__ == "__main__":
    main()
