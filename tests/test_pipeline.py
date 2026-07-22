"""Testes do pipeline.

Foco deliberado: as regras onde um erro passaria despercebido e contaminaria o dashboard
inteiro. Não testamos o pandas — testamos as decisões que tomamos sobre os dados.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config as cfg
from src.etl import _colunas_para_ler, _limpar_bloco
from src.features import construir_features


# ---------------------------------------------------------------------------------------
# Mapa de esquema — a proteção contra a mudança de formato do INEP
# ---------------------------------------------------------------------------------------

def test_q006_nao_e_renda_em_2024():
    """Q006 mudou de significado em 2024; renda familiar passou para Q007.

    Este é o erro mais perigoso do projeto: usar Q006 nos três anos produziria um
    gráfico de renda x nota plausível e errado. O teste trava essa regressão.
    """
    assert cfg.ESQUEMAS[2022].colunas["RENDA_FAMILIAR"] == "Q006"
    assert cfg.ESQUEMAS[2023].colunas["RENDA_FAMILIAR"] == "Q006"
    assert not cfg.ESQUEMAS[2024].tem("RENDA_FAMILIAR")


def test_edicao_2024_marcada_como_restrita():
    """2024 não permite cruzar perfil com nota; o resto do código depende dessa flag."""
    assert cfg.ESQUEMAS[2024].completo is False
    assert cfg.ESQUEMAS[2022].completo is True
    assert cfg.ESQUEMAS[2023].completo is True


def test_ano_sem_esquema_falha_alto():
    """Um ano desconhecido deve quebrar, não adivinhar nomes de coluna."""
    assert 2019 not in cfg.ESQUEMAS


def test_colunas_essenciais_ausentes_levantam_erro():
    esquema = cfg.ESQUEMAS[2023]
    header_incompleto = ["NU_INSCRICAO", "NU_ANO", "SG_UF_PROVA"]  # sem notas
    with pytest.raises(KeyError, match="essenciais ausentes"):
        _colunas_para_ler(esquema, header_incompleto)


def test_dtypes_cobrem_todas_as_canonicas():
    """Toda coluna canônica declarada precisa ter dtype, senão o pandas infere e infla RAM."""
    for esquema in cfg.ESQUEMAS.values():
        faltando = set(esquema.canonicas) - set(cfg.DTYPES_CANONICOS)
        assert not faltando, f"{esquema.ano}: sem dtype para {faltando}"


# ---------------------------------------------------------------------------------------
# Limpeza — a regra que define quem entra na análise
# ---------------------------------------------------------------------------------------

def _bloco_exemplo() -> pd.DataFrame:
    """Um caso por regra de descarte, na ordem em que aparecem em `_limpar_bloco`.

    idx  situação                                              sobrevive?
     0   tudo válido                                              sim
     1   faltou no dia 1 (presença 0)                             não
     2   eliminado em Matemática (presença 2)                     não
     3   presente, mas sem UF                                     não
     4   presente, zero em UMA objetiva (defeito pontual)         sim, com NaN em CN
     5   presente, zero em TODAS as objetivas                     não
     6   presente, redação 0 (nota legítima)                      sim, com o zero
    """
    return pd.DataFrame({
        "ANO": [2023] * 7,
        "PRESENCA_CN": [1, 0, 1, 1, 1, 1, 1],
        "PRESENCA_CH": [1, 0, 1, 1, 1, 1, 1],
        "PRESENCA_LC": [1, 1, 1, 1, 1, 1, 1],
        "PRESENCA_MT": [1, 1, 2, 1, 1, 1, 1],
        "NOTA_CN": [500.0, 480.0, 510.0, 520.0, 0.0, 0.0, 505.0],
        "NOTA_CH": [520.0, 490.0, 530.0, 540.0, 495.0, 0.0, 515.0],
        "NOTA_LC": [530.0, 500.0, 540.0, 550.0, 505.0, 0.0, 525.0],
        "NOTA_MT": [540.0, 510.0, 550.0, 560.0, 515.0, 0.0, 535.0],
        "NOTA_REDACAO": [600.0, 700.0, 620.0, 640.0, 660.0, 680.0, 0.0],
        "UF_PROVA": ["SP", "RJ", "MG", None, "BA", "PR", "CE"],
    })


def test_mantem_apenas_presentes_nos_dois_dias():
    """Faltante e eliminado saem da base — incluí-los com nota zero enviesaria toda UF."""
    out = _limpar_bloco(_bloco_exemplo())
    assert len(out) == 3  # índices 0, 4 e 6
    assert (out["PRESENCA_CN"] == 1).all()
    assert (out["PRESENCA_MT"] == 1).all()


def test_nota_zero_nas_objetivas_vira_nulo():
    """Zero é impossível na TRI das objetivas (a escala parte de ~300): é dado defeituoso."""
    out = _limpar_bloco(_bloco_exemplo())
    # O participante do índice 4 zerou só CN: fica na base, com CN nulo e o resto intacto.
    assert out["NOTA_CN"].isna().sum() == 1
    assert out["NOTA_CH"].notna().all()


def test_participante_sem_nenhuma_objetiva_valida_e_descartado():
    """Zero em todas as objetivas é registro defeituoso inteiro, não nota baixa."""
    out = _limpar_bloco(_bloco_exemplo())
    assert len(out[out[["NOTA_CN", "NOTA_CH", "NOTA_LC", "NOTA_MT"]].isna().all(axis=1)]) == 0


def test_nota_zero_na_redacao_e_preservada():
    """Na redação, 0 é nota legítima (fuga ao tema, anulada) e não pode virar nulo."""
    out = _limpar_bloco(_bloco_exemplo())
    assert (out["NOTA_REDACAO"] == 0.0).sum() == 1


def test_linha_sem_uf_e_descartada():
    out = _limpar_bloco(_bloco_exemplo())
    assert out["UF_PROVA"].notna().all()
    assert set(out["UF_PROVA"]) == {"SP", "BA", "CE"}


# ---------------------------------------------------------------------------------------
# Features — onde um erro silencioso mudaria a conclusão
# ---------------------------------------------------------------------------------------

def _base_features() -> pd.DataFrame:
    return pd.DataFrame({
        "ANO": [2023] * 6,
        "NOTA_CN": [400.0, 500.0, 600.0, 700.0, 800.0, 450.0],
        "NOTA_CH": [400.0, 500.0, 600.0, 700.0, 800.0, 450.0],
        "NOTA_LC": [400.0, 500.0, 600.0, 700.0, 800.0, 450.0],
        "NOTA_MT": [400.0, 500.0, 600.0, 700.0, 800.0, 450.0],
        "NOTA_REDACAO": [400.0, 500.0, 600.0, 700.0, 800.0, 450.0],
        "UF_PROVA": ["SP", "RJ", "MG", "BA", "AM", "SP"],
        "SEXO": ["M", "F", "M", "F", "M", "F"],
        "COR_RACA": [1, 2, 3, 1, 2, 3],
        "TIPO_ESCOLA": [2, 3, 2, 3, 2, 1],
        "DEPENDENCIA_ADM": [2.0, 4.0, 2.0, 4.0, 1.0, None],
        "RENDA_FAMILIAR": ["A", "Q", "F", "M", "B", "C"],
        "EDICAO_COMPLETA": [True] * 6,
    })


def test_media_geral_inclui_redacao_e_objetivas_nao():
    df = construir_features(_base_features())
    linha = df.iloc[0]
    assert linha["NOTA_MEDIA_OBJETIVAS"] == pytest.approx(400.0)
    assert linha["NOTA_MEDIA_GERAL"] == pytest.approx(400.0)

    # Com redação diferente das objetivas, as duas médias precisam divergir.
    base = _base_features()
    base.loc[0, "NOTA_REDACAO"] = 900.0
    df2 = construir_features(base)
    assert df2.iloc[0]["NOTA_MEDIA_OBJETIVAS"] == pytest.approx(400.0)
    assert df2.iloc[0]["NOTA_MEDIA_GERAL"] == pytest.approx(500.0)


def test_renda_mapeia_para_salarios_minimos_e_nao_reais():
    """Usar SM (e não reais) é o que torna as edições comparáveis apesar do reajuste anual."""
    df = construir_features(_base_features())
    assert df.loc[0, "RENDA_SM_PONTO_MEDIO"] == 0.0      # A = nenhuma renda
    assert df.loc[1, "RENDA_SM_PONTO_MEDIO"] == 22.5     # Q = acima de 20 SM
    assert df.loc[0, "RENDA_GRUPO"] == "Sem renda"


def test_renda_grupo_e_categorica_ordenada():
    """Sem ordem, "Até 1 SM" apareceria depois de "Acima de 10 SM" em qualquer eixo."""
    df = construir_features(_base_features())
    assert df["RENDA_GRUPO"].dtype.ordered
    ordem = list(df["RENDA_GRUPO"].dtype.categories)
    assert ordem == [c for c in cfg.ORDEM_RENDA_GRUPO if c in ordem]


def test_rede_agrupa_federal_estadual_municipal_como_publica():
    df = construir_features(_base_features())
    assert df.loc[0, "REDE"] == "Pública"    # estadual
    assert df.loc[1, "REDE"] == "Privada"
    assert df.loc[4, "REDE"] == "Pública"    # federal
    assert pd.isna(df.loc[5, "REDE"])        # sem pareamento com o Censo Escolar


def test_tipo_escola_nao_informado_e_categoria_e_nao_ausente():
    """A não-resposta é informativa (correlaciona com já ter concluído o EM)."""
    df = construir_features(_base_features())
    assert df.loc[5, "TIPO_ESCOLA_DESC"] == "Não informado"


def test_faixa_nota_usa_corte_absoluto_estavel_entre_anos():
    """FAIXA_NOTA precisa ser absoluta; se virasse relativa, a comparação temporal morre."""
    df = construir_features(_base_features())
    assert df.loc[0, "FAIXA_NOTA"] == "Até 400"
    assert df.loc[4, "FAIXA_NOTA"] == "Acima de 700"


def test_quintil_e_relativo_dentro_do_ano():
    """Quintil recalculado por ano: sempre ~20% em cada, por construção."""
    df = construir_features(_base_features())
    assert df["QUINTIL_DESEMPENHO"].notna().all()
    assert df.loc[df["NOTA_MEDIA_GERAL"].idxmax(), "QUINTIL_DESEMPENHO"] == "Q5 (mais alto)"


def test_regiao_cobre_todas_as_27_ufs():
    assert len(cfg.UF_REGIAO) == 27
    assert len(cfg.UF_NOME) == 27
    assert set(cfg.UF_REGIAO) == set(cfg.UF_NOME)


# ---------------------------------------------------------------------------------------
# Artefatos gerados — só rodam se o pipeline já foi executado
# ---------------------------------------------------------------------------------------

pytestmark_dados = pytest.mark.skipif(
    not (cfg.OUTPUTS_TABLEAU / "enem_amostra.csv").exists(),
    reason="artefatos ainda não gerados — rode `make all`",
)


@pytestmark_dados
def test_amostra_e_representativa_da_base_completa():
    """A amostra autoponderada deve reproduzir a média da base com folga de 2 pontos.

    Este teste é a garantia de que o boxplot do dashboard não está mostrando uma
    distribuição deslocada em relação à realidade.
    """
    amostra = pd.read_csv(cfg.OUTPUTS_TABLEAU / "enem_amostra.csv")
    uf = pd.read_csv(cfg.DATA_PROCESSED / "agg_uf.csv")

    for ano in amostra["ANO"].unique():
        media_amostra = amostra.loc[amostra.ANO == ano, "NOTA_MEDIA_GERAL"].mean()
        sub = uf[uf.ANO == ano]
        media_real = (sub.nota_media_geral * sub.n_participantes).sum() / sub.n_participantes.sum()
        assert abs(media_amostra - media_real) < 2.0, (
            f"{ano}: amostra {media_amostra:.2f} vs base {media_real:.2f}"
        )


@pytestmark_dados
def test_agregados_nao_expoem_grupos_pequenos():
    """Grupos abaixo do mínimo devem estar suprimidos — instabilidade e risco de reidentificação."""
    for caminho in cfg.DATA_PROCESSED.glob("agg_*.csv"):
        df = pd.read_csv(caminho)
        if "n_participantes" in df.columns and caminho.name != "agg_faixas.csv":
            assert (df["n_participantes"] >= 30).all(), caminho.name


@pytestmark_dados
def test_amostra_nao_tem_renda_em_2024():
    """Se renda aparecer em 2024, alguém religou um join que o INEP tornou impossível."""
    amostra = pd.read_csv(cfg.OUTPUTS_TABLEAU / "enem_amostra.csv")
    assert amostra.loc[amostra.ANO == 2024, "RENDA_GRUPO"].isna().all()
