"""Configuração central do projeto: caminhos, fontes de dados e dicionários de decodificação.

Concentrar tudo aqui evita que caminhos e mapeamentos fiquem espalhados pelo ETL e
pelo notebook — o notebook importa daqui em vez de redefinir constantes.
"""

from __future__ import annotations

from pathlib import Path

# --------------------------------------------------------------------------------------
# Caminhos
# --------------------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent

DATA_RAW = ROOT / "data" / "raw"            # .zip baixado do INEP (nunca versionado)
DATA_INTERIM = ROOT / "data" / "interim"    # CSV extraído + parquet intermediário
DATA_PROCESSED = ROOT / "data" / "processed"  # saídas finais, prontas para consumo
OUTPUTS = ROOT / "outputs"
OUTPUTS_FIGURES = OUTPUTS / "figures"
OUTPUTS_TABLEAU = OUTPUTS / "tableau"

for _p in (DATA_RAW, DATA_INTERIM, DATA_PROCESSED, OUTPUTS_FIGURES, OUTPUTS_TABLEAU):
    _p.mkdir(parents=True, exist_ok=True)

# --------------------------------------------------------------------------------------
# Fonte dos dados
# --------------------------------------------------------------------------------------
# Portal oficial (página de navegação, com dicionário e notas técnicas de cada edição):
#   https://www.gov.br/inep/pt-br/acesso-a-informacao/dados-abertos/microdados/enem
# Os .zip ficam num host de download separado. URLs verificadas via HEAD em 2026-07-22.

INEP_PORTAL = "https://www.gov.br/inep/pt-br/acesso-a-informacao/dados-abertos/microdados/enem"

MICRODADOS_URL = "https://download.inep.gov.br/microdados/microdados_enem_{ano}.zip"

# Tamanho esperado do .zip (bytes), obtido do Content-Length no momento da verificação.
# Serve como sanity check pós-download: arquivo truncado é a falha mais comum num
# download de meia hora em conexão instável, e ela é silenciosa se ninguém checar.
TAMANHO_ESPERADO_ZIP = {
    2022: 620_743_609,
    2023: 549_511_687,
    2024: 526_073_856,
    2025: 630_250_096,
}

ANOS = (2022, 2023, 2024)  # edições usadas no comparativo

# --------------------------------------------------------------------------------------
# Mapa de esquema por edição
# --------------------------------------------------------------------------------------
# O INEP mudou o formato dos microdados entre 2023 e 2024, de duas formas que quebram
# qualquer código que assuma nomes fixos de coluna:
#
#   1) PARTICIPAÇÃO x RESULTADO — até 2023 o pacote era um CSV único por participante.
#      Em 2024 virou PARTICIPANTES_2024.csv (perfil) + RESULTADOS_2024.csv (notas), e o
#      dicionário oficial afirma, sobre NU_SEQUENCIAL: "Variável distinta da NU_INSCRICAO
#      disponível na base de Participantes, de modo que não é possível utilizá-la para
#      relacionar as duas bases." Ou seja, em 2024 NÃO EXISTE cruzamento individual entre
#      questionário socioeconômico e nota. Isso não é limitação do nosso pipeline: é
#      anonimização deliberada do INEP.
#
#   2) RENUMERAÇÃO DO QUESTIONÁRIO — Q006 era "renda mensal da família" até 2023 e passou
#      a ser "Você possui renda?" em 2024, com a renda familiar movida para Q007. O tipo
#      de escola saiu de TP_ESCOLA e virou Q023. Um pipeline que lesse "Q006" nos três
#      anos produziria um gráfico de renda x nota plausível e ERRADO em 2024.
#
# Por isso o ETL nunca referencia nome cru: trabalha com nomes canônicos e traduz via
# este mapa. Ano sem entrada aqui provoca erro explícito em vez de silêncio.

CANONICO_PADRAO_ATE_2023 = {
    # canônico              # nome cru no CSV
    "ID": "NU_INSCRICAO",
    "ANO": "NU_ANO",
    "FAIXA_ETARIA": "TP_FAIXA_ETARIA",
    "SEXO": "TP_SEXO",
    "COR_RACA": "TP_COR_RACA",
    "ST_CONCLUSAO": "TP_ST_CONCLUSAO",
    "TREINEIRO": "IN_TREINEIRO",
    "TIPO_ESCOLA": "TP_ESCOLA",
    "DEPENDENCIA_ADM": "TP_DEPENDENCIA_ADM_ESC",
    "LOCALIZACAO_ESC": "TP_LOCALIZACAO_ESC",
    "UF_ESC": "SG_UF_ESC",
    "UF_PROVA": "SG_UF_PROVA",
    "PRESENCA_CN": "TP_PRESENCA_CN",
    "PRESENCA_CH": "TP_PRESENCA_CH",
    "PRESENCA_LC": "TP_PRESENCA_LC",
    "PRESENCA_MT": "TP_PRESENCA_MT",
    "NOTA_CN": "NU_NOTA_CN",
    "NOTA_CH": "NU_NOTA_CH",
    "NOTA_LC": "NU_NOTA_LC",
    "NOTA_MT": "NU_NOTA_MT",
    "NOTA_REDACAO": "NU_NOTA_REDACAO",
    "STATUS_REDACAO": "TP_STATUS_REDACAO",
    "LINGUA": "TP_LINGUA",
    "ESCOLARIDADE_PAI": "Q001",
    "ESCOLARIDADE_MAE": "Q002",
    "PESSOAS_RESIDENCIA": "Q005",
    "RENDA_FAMILIAR": "Q006",
}

# 2024: só a base de RESULTADOS é utilizável para análise de desempenho, porque é a
# única que tem nota. Sem TIPO_ESCOLA (que virou Q023, do outro lado da parede) o
# recorte público x privado passa a sair de DEPENDENCIA_ADM — ver nota em MAP_DEPENDENCIA.
CANONICO_RESULTADOS_2024 = {
    "ID": "NU_SEQUENCIAL",
    "ANO": "NU_ANO",
    "DEPENDENCIA_ADM": "TP_DEPENDENCIA_ADM_ESC",
    "LOCALIZACAO_ESC": "TP_LOCALIZACAO_ESC",
    "UF_ESC": "SG_UF_ESC",
    "UF_PROVA": "SG_UF_PROVA",
    "PRESENCA_CN": "TP_PRESENCA_CN",
    "PRESENCA_CH": "TP_PRESENCA_CH",
    "PRESENCA_LC": "TP_PRESENCA_LC",
    "PRESENCA_MT": "TP_PRESENCA_MT",
    "NOTA_CN": "NU_NOTA_CN",
    "NOTA_CH": "NU_NOTA_CH",
    "NOTA_LC": "NU_NOTA_LC",
    "NOTA_MT": "NU_NOTA_MT",
    "NOTA_REDACAO": "NU_NOTA_REDACAO",
    "STATUS_REDACAO": "TP_STATUS_REDACAO",
    "LINGUA": "TP_LINGUA",
}


class EsquemaEdicao:
    """Descreve como ler uma edição específica dos microdados.

    `completo=False` sinaliza que a edição não permite cruzar perfil socioeconômico
    com nota — o ETL, o notebook e os agregados consultam esse atributo em vez de
    checar o ano na mão espalhado pelo código.
    """

    def __init__(self, ano, padrao_csv, colunas, completo, observacao=""):
        self.ano = ano
        self.padrao_csv = padrao_csv     # trecho do nome do CSV dentro do zip
        self.colunas = colunas           # canônico -> cru
        self.completo = completo
        self.observacao = observacao

    @property
    def canonicas(self):
        return list(self.colunas)

    def crua(self, canonico):
        return self.colunas[canonico]

    def tem(self, canonico):
        return canonico in self.colunas


ESQUEMAS = {
    2022: EsquemaEdicao(
        2022, "MICRODADOS_ENEM_2022", CANONICO_PADRAO_ATE_2023, completo=True,
        observacao="Arquivo único. Reeditado pelo INEP em 08/2024 com ajustes na base de itens.",
    ),
    2023: EsquemaEdicao(
        2023, "MICRODADOS_ENEM_2023", CANONICO_PADRAO_ATE_2023, completo=True,
        observacao="Arquivo único, mesmo esquema de 2022.",
    ),
    2024: EsquemaEdicao(
        2024, "RESULTADOS_2024", CANONICO_RESULTADOS_2024, completo=False,
        observacao=(
            "Base dividida em PARTICIPANTES + RESULTADOS sem chave comum. Só notas, UF e "
            "rede da escola são analisáveis; renda, sexo e cor/raça não se ligam à nota."
        ),
    ),
}

CANONICAS_NOTA = ["NOTA_CN", "NOTA_CH", "NOTA_LC", "NOTA_MT", "NOTA_REDACAO"]
CANONICAS_PRESENCA = ["PRESENCA_CN", "PRESENCA_CH", "PRESENCA_LC", "PRESENCA_MT"]

# Tipos por nome CANÔNICO — o ETL traduz para os nomes crus na hora de ler. Sem isso o
# pandas infere float64 para tudo e o consumo de RAM triplica; códigos são categorias,
# não números para somar.
DTYPES_CANONICOS = {
    "ID": "string",
    "ANO": "int16",
    "FAIXA_ETARIA": "int8",
    "SEXO": "category",
    "COR_RACA": "int8",
    "ST_CONCLUSAO": "int8",
    "TREINEIRO": "int8",
    "TIPO_ESCOLA": "int8",
    "DEPENDENCIA_ADM": "float32",   # ausente para quem não foi pareado ao Censo Escolar
    "LOCALIZACAO_ESC": "float32",
    "UF_ESC": "category",
    "UF_PROVA": "category",
    "PRESENCA_CN": "int8",
    "PRESENCA_CH": "int8",
    "PRESENCA_LC": "int8",
    "PRESENCA_MT": "int8",
    "NOTA_CN": "float32",
    "NOTA_CH": "float32",
    "NOTA_LC": "float32",
    "NOTA_MT": "float32",
    "NOTA_REDACAO": "float32",
    "STATUS_REDACAO": "float32",
    "LINGUA": "float32",
    "ESCOLARIDADE_PAI": "category",
    "ESCOLARIDADE_MAE": "category",
    "PESSOAS_RESIDENCIA": "float32",
    "RENDA_FAMILIAR": "category",
}

# --------------------------------------------------------------------------------------
# Dicionários de decodificação (fonte: "Dicionário_Microdados_Enem_<ano>.xlsx" do INEP)
# --------------------------------------------------------------------------------------

MAP_SEXO = {"M": "Masculino", "F": "Feminino"}

MAP_COR_RACA = {
    0: "Não declarado",
    1: "Branca",
    2: "Preta",
    3: "Parda",
    4: "Amarela",
    5: "Indígena",
    6: "Não dispõe da informação",
}

# TP_ESCOLA descreve o tipo de escola do ENSINO MÉDIO declarado pelo participante.
# O código 1 ("Não respondeu") é a maioria absoluta da base: quem já concluiu o EM
# normalmente não responde. Tratar isso como categoria própria e NÃO como ausente
# é o ponto mais importante da limpeza — ver README, seção Limitações.
MAP_ESCOLA = {
    1: "Não informado",
    2: "Pública",
    3: "Privada",
    4: "Exterior",
}

# TP_DEPENDENCIA_ADM_ESC vem do pareamento com o Censo Escolar, não de autodeclaração:
# só é preenchido para quem o INEP identificou como provável concluinte do EM naquele
# ano. Cobre uma fração da base — mas é a ÚNICA variável de rede de ensino disponível em
# 2024, então é ela que sustenta o recorte público x privado comparável entre as três
# edições. Para 2022/2023 mantemos TIPO_ESCOLA em paralelo, que é autodeclarada e cobre
# outro conjunto de participantes. As duas NÃO são intercambiáveis — ver README.
MAP_DEPENDENCIA = {
    1.0: "Federal",
    2.0: "Estadual",
    3.0: "Municipal",
    4.0: "Privada",
}

# Agrupamento binário derivado da dependência administrativa. É o recorte que aparece no
# boxplot do dashboard e o único comparável nas três edições.
MAP_REDE = {
    "Federal": "Pública",
    "Estadual": "Pública",
    "Municipal": "Pública",
    "Privada": "Privada",
}

MAP_LOCALIZACAO_ESC = {1.0: "Urbana", 2.0: "Rural"}

MAP_FAIXA_ETARIA = {
    1: "Menor de 17 anos",
    2: "17 anos",
    3: "18 anos",
    4: "19 anos",
    5: "20 anos",
    6: "21 anos",
    7: "22 anos",
    8: "23 anos",
    9: "24 anos",
    10: "25 anos",
    11: "26 a 30 anos",
    12: "31 a 35 anos",
    13: "36 a 40 anos",
    14: "41 a 45 anos",
    15: "46 a 50 anos",
    16: "51 a 55 anos",
    17: "56 a 60 anos",
    18: "61 a 65 anos",
    19: "66 a 70 anos",
    20: "Maior de 70 anos",
}

MAP_ST_CONCLUSAO = {
    1: "Já concluí o Ensino Médio",
    2: "Concluirei em {ano}",
    3: "Concluirei após {ano}",
    4: "Não concluí e não estou cursando",
}

# Q006 — renda familiar mensal. O INEP expressa a faixa em reais, e o valor nominal
# muda a cada ano (acompanha o salário mínimo). Para comparar 2023 com 2024 usamos a
# faixa em MÚLTIPLOS DE SALÁRIO MÍNIMO, que é estável entre edições — comparar reais
# nominais entre anos introduziria um viés de inflação puro.
MAP_RENDA_SM = {
    "A": "Nenhuma renda",
    "B": "Até 1 SM",
    "C": "1 a 1,5 SM",
    "D": "1,5 a 2 SM",
    "E": "2 a 2,5 SM",
    "F": "2,5 a 3 SM",
    "G": "3 a 4 SM",
    "H": "4 a 5 SM",
    "I": "5 a 6 SM",
    "J": "6 a 7 SM",
    "K": "7 a 8 SM",
    "L": "8 a 9 SM",
    "M": "9 a 10 SM",
    "N": "10 a 12 SM",
    "O": "12 a 15 SM",
    "P": "15 a 20 SM",
    "Q": "Acima de 20 SM",
}

# Agrupamento em 6 faixas para os gráficos — 17 categorias no eixo de um dashboard
# viram ruído visual, e as faixas altas têm poucos participantes.
MAP_RENDA_GRUPO = {
    "A": "Sem renda",
    "B": "Até 1 SM",
    "C": "1 a 2 SM", "D": "1 a 2 SM",
    "E": "2 a 3 SM", "F": "2 a 3 SM",
    "G": "3 a 5 SM", "H": "3 a 5 SM",
    "I": "5 a 10 SM", "J": "5 a 10 SM", "K": "5 a 10 SM",
    "L": "5 a 10 SM", "M": "5 a 10 SM",
    "N": "Acima de 10 SM", "O": "Acima de 10 SM",
    "P": "Acima de 10 SM", "Q": "Acima de 10 SM",
}

# Ordem para eixos categóricos (o Tableau ordena alfabeticamente por padrão, o que
# colocaria "Até 1 SM" depois de "Acima de 10 SM").
ORDEM_RENDA_GRUPO = [
    "Sem renda", "Até 1 SM", "1 a 2 SM", "2 a 3 SM",
    "3 a 5 SM", "5 a 10 SM", "Acima de 10 SM",
]

# Ponto médio da faixa em salários mínimos — variável NUMÉRICA para regressão e para
# o scatter renda x nota no Tableau. "Nenhuma renda" = 0; a faixa aberta do topo
# recebe 22,5 (estimativa conservadora, documentada como limitação).
RENDA_PONTO_MEDIO_SM = {
    "A": 0.0, "B": 0.5, "C": 1.25, "D": 1.75, "E": 2.25, "F": 2.75,
    "G": 3.5, "H": 4.5, "I": 5.5, "J": 6.5, "K": 7.5, "L": 8.5,
    "M": 9.5, "N": 11.0, "O": 13.5, "P": 17.5, "Q": 22.5,
}

MAP_ESCOLARIDADE_PAIS = {
    "A": "Nunca estudou",
    "B": "Fundamental I incompleto",
    "C": "Fundamental II incompleto",
    "D": "Médio incompleto",
    "E": "Médio completo",
    "F": "Superior completo",
    "G": "Pós-graduação",
    "H": "Não sei",
}

MAP_SIM_NAO_Q025 = {"A": "Não", "B": "Sim"}

MAP_LINGUA = {0.0: "Inglês", 1.0: "Espanhol"}

# Regiões — o CSV traz só a UF; a região é derivada e é um recorte que o Tableau
# usa como filtro hierárquico (Região > UF).
UF_REGIAO = {
    "AC": "Norte", "AP": "Norte", "AM": "Norte", "PA": "Norte",
    "RO": "Norte", "RR": "Norte", "TO": "Norte",
    "AL": "Nordeste", "BA": "Nordeste", "CE": "Nordeste", "MA": "Nordeste",
    "PB": "Nordeste", "PE": "Nordeste", "PI": "Nordeste", "RN": "Nordeste",
    "SE": "Nordeste",
    "DF": "Centro-Oeste", "GO": "Centro-Oeste", "MT": "Centro-Oeste",
    "MS": "Centro-Oeste",
    "ES": "Sudeste", "MG": "Sudeste", "RJ": "Sudeste", "SP": "Sudeste",
    "PR": "Sul", "RS": "Sul", "SC": "Sul",
}

UF_NOME = {
    "AC": "Acre", "AL": "Alagoas", "AP": "Amapá", "AM": "Amazonas",
    "BA": "Bahia", "CE": "Ceará", "DF": "Distrito Federal",
    "ES": "Espírito Santo", "GO": "Goiás", "MA": "Maranhão",
    "MT": "Mato Grosso", "MS": "Mato Grosso do Sul", "MG": "Minas Gerais",
    "PA": "Pará", "PB": "Paraíba", "PR": "Paraná", "PE": "Pernambuco",
    "PI": "Piauí", "RJ": "Rio de Janeiro", "RN": "Rio Grande do Norte",
    "RS": "Rio Grande do Sul", "RO": "Rondônia", "RR": "Roraima",
    "SC": "Santa Catarina", "SP": "São Paulo", "SE": "Sergipe",
    "TO": "Tocantins",
}

# Nome legível de cada área — usado ao "derreter" as notas para formato longo,
# que é o formato que o Tableau prefere para gráfico de barras por área.
AREAS = {
    "NOTA_CN": "Ciências da Natureza",
    "NOTA_CH": "Ciências Humanas",
    "NOTA_LC": "Linguagens e Códigos",
    "NOTA_MT": "Matemática",
    "NOTA_REDACAO": "Redação",
}

# --------------------------------------------------------------------------------------
# Parâmetros de processamento
# --------------------------------------------------------------------------------------

CHUNKSIZE = 200_000        # linhas por bloco de leitura (~cabe folgado em RAM)
TAMANHO_AMOSTRA = 200_000  # linhas da amostra estratificada final
SEED = 42                  # reprodutibilidade da amostragem
