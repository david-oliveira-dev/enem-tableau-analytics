"""Mantém o TABLEAU_BLUEPRINT.md em sincronia com os dados realmente exportados.

O blueprint é escrito à mão e o pipeline evolui: nada impede que uma coluna seja
renomeada em `src/` e o documento continue mandando o usuário arrastar um campo que não
existe mais. O erro só apareceria com o Tableau já aberto, e sem mensagem útil — campo
inexistente vira nulo silencioso.

Estes testes fecham esse ciclo: todo campo entre colchetes no blueprint precisa existir
em algum arquivo de `outputs/tableau/`, e todo valor literal comparado numa fórmula
precisa aparecer de fato na coluna correspondente.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config as cfg

BLUEPRINT = cfg.ROOT / "TABLEAU_BLUEPRINT.md"

pytestmark = pytest.mark.skipif(
    not (cfg.OUTPUTS_TABLEAU / "enem_amostra.csv").exists(),
    reason="artefatos ainda não gerados — rode `make all`",
)


def _normalizar(nome: str) -> str:
    """Reduz um nome de campo à forma comparável.

    O Tableau exibe `nota_media_geral` como "Nota Media Geral" — troca underscore por
    espaço e ajusta maiúsculas. Em vez de replicar essa regra (que varia com a versão),
    comparamos só letras e dígitos em minúsculas: pega o erro de digitação de verdade
    sem falso positivo por convenção de exibição.
    """
    return re.sub(r"[^a-z0-9]", "", nome.lower())


def _colunas_exportadas() -> dict[str, set[str]]:
    """{arquivo: {colunas normalizadas}} para tudo em outputs/tableau/."""
    out = {}
    for caminho in sorted(cfg.OUTPUTS_TABLEAU.glob("*.csv")):
        colunas = pd.read_csv(caminho, nrows=0).columns
        out[caminho.stem] = {_normalizar(c) for c in colunas}
    return out


# Campos que o blueprint define ELE MESMO como campos calculados ou parâmetros — não
# existem nos arquivos por definição, e é correto que não existam.
CAMPOS_DERIVADOS = {
    "mediaponderada", "gapprivadapublica", "rotulogap", "cordesvionacional",
    "chancequintilsuperior", "razaodeacessoaotopo", "notaselecionada",
    "acimadocorte", "faixaetariaordenada", "avisocobertura",
    "pano", "parea", "pnotacorte", "pescalamapa",
    "geografia",  # hierarquia criada no Tableau
}


def _sem_diagramas(texto: str) -> str:
    """Remove os blocos de código que desenham o layout em arte ASCII.

    O diagrama do dashboard usa colchetes como caixas (`[ Nota média ] [ Gap ]`), o que
    o extrator confundiria com referência de campo. Identificamos esses blocos pelos
    caracteres de moldura, que não aparecem em nenhuma fórmula.
    """
    blocos = re.split(r"(```.*?```)", texto, flags=re.DOTALL)
    return "".join(b for b in blocos if not any(c in b for c in "┌│└├┬┴┼─"))


def _campos_citados() -> set[str]:
    """Todo `[Campo]` que aparece no blueprint, normalizado."""
    texto = _sem_diagramas(BLUEPRINT.read_text(encoding="utf-8"))
    # Só nos interessam referências em colchetes, que é como o Tableau nomeia campo
    # dentro de uma fórmula.
    return {_normalizar(m) for m in re.findall(r"\[([A-Za-zÀ-ÿ0-9 _]+)\]", texto)}


def test_todo_campo_do_blueprint_existe_em_algum_arquivo():
    """Nenhuma fórmula pode referenciar campo que não foi exportado."""
    exportadas = _colunas_exportadas()
    universo = set().union(*exportadas.values())

    orfaos = sorted(
        c for c in _campos_citados()
        if c and c not in universo and c not in CAMPOS_DERIVADOS
    )
    assert not orfaos, (
        f"Campos citados no blueprint que não existem em outputs/tableau/: {orfaos}. "
        "Renomeie no blueprint ou exporte a coluna."
    )


def test_valores_literais_das_formulas_existem_nos_dados():
    """`[Rede] = \"Pública\"` só funciona se a string bater exatamente — inclusive o acento.

    Este é o erro que motivou o teste: a fórmula do KPI principal comparava com
    "Publica" sem acento e devolveria nulo, sem erro nenhum, com o dashboard já montado.
    """
    texto = BLUEPRINT.read_text(encoding="utf-8")
    amostra = pd.read_csv(
        cfg.OUTPUTS_TABLEAU / "enem_amostra.csv",
        usecols=["REDE", "QUINTIL_DESEMPENHO", "RENDA_GRUPO", "FAIXA_NOTA"],
    )

    # {coluna: literais que o blueprint compara contra ela}
    esperado = {
        "REDE": re.findall(r'\[Rede\]\s*=\s*"([^"]+)"', texto),
        "QUINTIL_DESEMPENHO": re.findall(r'\[Quintil Desempenho\]\s*=\s*"([^"]+)"', texto),
    }

    for coluna, literais in esperado.items():
        validos = set(amostra[coluna].dropna().unique())
        assert literais, f"nenhum literal encontrado para {coluna} — regex desatualizada?"
        for literal in literais:
            assert literal in validos, (
                f'{coluna}: o blueprint compara com "{literal}", mas os valores reais '
                f"são {sorted(validos)}. No Tableau isso devolve nulo silenciosamente."
            )


def test_ordenacoes_manuais_cobrem_as_categorias_reais():
    """A seção 8 lista a ordem manual de cada categórica; ela precisa estar completa.

    O `.hyper` não guarda ordem de categórica, então essa lista é a única fonte da
    ordenação correta no Tableau. Se uma categoria faltar nela, o eixo sai fora de ordem.
    """
    texto = BLUEPRINT.read_text(encoding="utf-8")
    amostra = pd.read_csv(
        cfg.OUTPUTS_TABLEAU / "enem_amostra.csv",
        usecols=["RENDA_GRUPO", "FAIXA_NOTA", "QUINTIL_DESEMPENHO"],
    )

    for coluna in ("RENDA_GRUPO", "FAIXA_NOTA", "QUINTIL_DESEMPENHO"):
        for categoria in amostra[coluna].dropna().unique():
            assert f"`{categoria}`" in texto, (
                f"{coluna}: categoria '{categoria}' não aparece na seção de ordenação "
                "manual do blueprint — o eixo sairia fora de ordem no Tableau."
            )


def test_tabelas_prometidas_pelo_blueprint_foram_exportadas():
    """A seção 1 promete um conjunto de tabelas; todas precisam existir."""
    texto = BLUEPRINT.read_text(encoding="utf-8")
    exportadas = set(_colunas_exportadas())

    prometidas = set(re.findall(r"`(agg_[a-z_]+)`", texto))
    faltando = sorted(prometidas - exportadas)
    assert not faltando, f"blueprint cita tabelas inexistentes: {faltando}"
