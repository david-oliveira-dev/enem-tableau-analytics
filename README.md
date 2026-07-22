# ENEM 2022–2024 — pipeline de dados para Tableau

Pipeline em Python que transforma os microdados brutos do ENEM (4,7 GB, três edições) em
artefatos prontos para um dashboard do Tableau Public: um extract `.hyper`, CSVs limpos e
um blueprint de montagem passo a passo.

**Este repositório não contém o dashboard.** Ele contém tudo o que alimenta o dashboard,
mais a especificação para montá-lo — ver [`TABLEAU_BLUEPRINT.md`](TABLEAU_BLUEPRINT.md).

---

## Contexto

Que o desempenho no ENEM é desigual não é notícia. A pergunta que orienta o projeto é
outra: **qual recorte concentra mais desigualdade, e algum deles se moveu ao longo do
tempo?** Um painel que só mostra "privada tira mais que pública" não muda decisão nenhuma.
Um que mostra *onde* a diferença se concentra e *se está crescendo* orienta onde alocar
esforço.

### O que os dados mostraram

| # | Achado | Número |
|---|---|---|
| 1 | O gap entre rede privada e pública cresceu nas três edições | 89,5 → 97,7 → **103,3** pontos |
| 2 | Redação é o maior separador entre redes — mais do triplo de Linguagens | **173,0** vs 55,6 pontos |
| 3 | A nota sobe de forma quase linear com a renda, sem platô no topo | 480 → **637** pontos (157 de amplitude) |
| 4 | Matemática é a área mais sensível à renda | **215** pontos entre a faixa mais pobre e a mais rica |
| 5 | A desigualdade territorial não se moveu em três anos | amplitude entre UFs: 63,6 / 64,8 / **65,2** pontos |

Traduzido em acesso ao topo, que é o que decide vaga: **50,5%** dos alunos de escola
privada chegam ao quintil superior, contra **12,1%** da rede pública — razão de 4,2 para 1.
Por renda, a razão vai a **13,8 para 1**.

O raciocínio completo, com os gráficos e as ressalvas, está em
[`notebooks/01_eda_enem.ipynb`](notebooks/01_eda_enem.ipynb).

---

## Decisões técnicas

As que mudam o resultado, e por quê.

### 1. Só entram participantes presentes nos dois dias

Quem faltou aparece no CSV original com nota **vazia**, não com zero. Preencher esse vazio
com zero — o erro clássico deste dataset — derrubaria a média de cada UF proporcionalmente
à sua taxa de abstenção, convertendo *"onde as pessoas faltam mais"* em *"onde as pessoas
vão pior"*. Com abstenção acima de 30%, o viés seria enorme.

Custo: a base cai de 10,7 milhões de inscritos para 8,0 milhões de participantes
efetivos (67–69% por edição). É a população correta para falar de desempenho.

### 2. Nomes canônicos e mapa de esquema por edição

O INEP mudou o formato entre 2023 e 2024 de duas formas que quebram qualquer código com
nomes de coluna fixos:

- **`Q006` trocou de significado.** Era "renda mensal da família" até 2023; em 2024 virou
  "Você possui renda?", com a renda familiar movida para `Q007`. O tipo de escola saiu de
  `TP_ESCOLA` e virou `Q023`.
- **A base foi partida em duas** — `PARTICIPANTES_2024.csv` e `RESULTADOS_2024.csv`.

Um pipeline que lesse `Q006` nos três anos produziria um gráfico de renda × nota
**plausível e errado** em 2024. Por isso nenhum módulo referencia nome cru: tudo passa por
`ESQUEMAS` em [`src/config.py`](src/config.py), que traduz para nomes canônicos. Ano sem
entrada no mapa provoca erro explícito, nunca adivinhação. Há teste travando essa
regressão (`test_q006_nao_e_renda_em_2024`).

### 3. Duas granularidades de saída, com papéis distintos

| Arquivo | O que é | Papel |
|---|---|---|
| `agg_*.csv` | Agregados sobre os **8,0 milhões** de participantes | Mapa, KPIs, séries — onde o número precisa estar exato |
| `enem_amostra.csv` | **200 mil** linhas, 1 por participante | Boxplot, histograma, scatter — onde importa a forma da distribuição |

Se o mapa saísse da amostra, exibiria estimativas com erro amostral formatadas com uma
casa decimal — precisão que a amostra não tem. Se o boxplot saísse do agregado, não haveria
quartis para desenhar. Daí as duas.

A amostra é **estratificada proporcionalmente por UF e autoponderada**: a fração de 2,5% é
idêntica em toda UF, então qualquer média tirada dela é estimador não-enviesado, sem
coluna de peso. Optamos por isso em vez de um piso mínimo por UF, que daria mais linhas a
Roraima ao custo de enviesar toda média nacional lida da amostra.

**Verificação:** média da amostra vs. base completa — 542,90 vs 543,64 (2022), 542,43 vs
541,88 (2023), 539,41 vs 539,49 (2024). Erro abaixo de 0,8 ponto, checado por teste
automatizado.

### 4. Renda em salários mínimos, não em reais

O INEP expressa as faixas de `Q006` em reais, e o valor nominal acompanha o salário mínimo
de cada ano. Comparar 2022 com 2023 em reais nominais mediria inflação, não desempenho.
Convertemos para múltiplos de salário mínimo, que são estáveis entre edições.

Para o scatter, a faixa vira número pelo **ponto médio em SM**. A faixa aberta do topo
("acima de 20 SM") recebe 22,5 — estimativa conservadora, e limitação assumida.

### 5. Faixa absoluta e quintil relativo são coisas diferentes

- `FAIXA_NOTA` usa cortes fixos de 100 pontos. Como o corte não muda, **é ela que permite
  comparar edições**.
- `QUINTIL_DESEMPENHO` é recalculado dentro de cada ano. Por construção, 20% da base
  sempre cai no quintil superior — **nunca mede evolução**, só posição relativa dentro do
  ano.

Trocar uma pela outra é o erro sutil mais provável nesta análise; os nomes são
deliberadamente distintos e cada uma tem teste próprio.

### 6. TLS: cadeia incompleta do INEP, corrigida sem desligar verificação

`download.inep.gov.br` envia apenas o certificado folha e **omite o intermediário**
(`RNP ICPEdu GR46 OV TLS CA 2025`). Qualquer cliente sem esse intermediário em cache falha
com `unable to get local issuer certificate` — curl, requests, urllib. O navegador funciona
porque busca o intermediário sozinho pela extensão AIA.

É erro de configuração do servidor, não conexão insegura. A correção certa é **fornecer o
intermediário**, não desativar a verificação: ele está versionado em `certs/` (obtido da
URL de AIA do próprio certificado) e encadeia até a GlobalSign Root R46, já confiável no
sistema. A assinatura continua verificada ponta a ponta. A flag `--insecure` existe como
último recurso e avisa quando usada.

---

## Limitações dos dados

Leia antes de citar qualquer número deste projeto.

**1. Em 2024 não existe cruzamento entre perfil e nota.** O INEP publicou perfil e
resultados em bases sem chave comum. O dicionário oficial afirma sobre `NU_SEQUENCIAL`:
*"Variável distinta da NU_INSCRICAO disponível na base de Participantes, de modo que não é
possível utilizá-la para relacionar as duas bases."* Renda, sexo e cor/raça de 2024 são
**estruturalmente inacessíveis** cruzados com nota. Marcados como nulos, nunca imputados.

**2. A cobertura da variável de rede saltou em 2024** — de 26,9% para 39,9%. `REDE` vem do
pareamento com o Censo Escolar e só existe para prováveis concluintes do EM. Como a
população comparada mudou de tamanho e possivelmente de perfil, **parte do aumento do gap
em 2024 é composição da base, não queda de desempenho**. A tendência 2022 → 2023 é sólida
(cobertura estável); o salto de 2024 deve ser lido como limite superior.

**3. Rede e tipo de escola medem coisas diferentes.** `REDE` vem do Censo Escolar;
`TIPO_ESCOLA` é autodeclarada no questionário e só existe até 2023. Cobrem conjuntos
distintos de participantes e **não são intercambiáveis**.

**4. "Não informado" em tipo de escola é categoria, não ausência.** É a maioria da base —
quem já concluiu o EM costuma não responder. A não-resposta é informativa; imputar ou
descartar distorceria o recorte.

**5. Renda e rede estão fortemente correlacionadas.** As análises de renda e de rede
descrevem, em boa medida, o mesmo fenômeno por ângulos diferentes. Separar os efeitos
exigiria modelagem que este projeto não faz — por isso entregamos `agg_renda_rede`, que
ao menos permite ver os dois eixos ao mesmo tempo.

**6. A média simples não é nota de corte.** SISU, ProUni e FIES aplicam pesos por curso.
`NOTA_MEDIA_GERAL` é escolha analítica explícita, não reprodução de cálculo oficial.

**7. Não há ranking de escolas.** O INEP mascara o código da escola quando há menos de 10
participantes; ranquear a partir de cobertura parcial produziria classificação injusta com
aparência de rigor. Grupos com menos de 30 participantes são suprimidos das tabelas
agregadas.

---

## Como reproduzir

Requer Python 3.10+, ~8 GB livres em disco e conexão para baixar 1,6 GB do INEP.

```bash
git clone <url-do-repo> && cd enem-tableau-analytics

python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

make all          # download → ETL → agregação → export → testes
```

Ou passo a passo:

```bash
make download     # baixa e extrai os 3 zips do INEP  (~7 min)
make etl          # CSV bruto → Parquet harmonizado    (~2 min)
make aggregate    # tabelas agregadas da base completa (~1 min)
make export       # amostra + CSV + extract .hyper     (~1 min)
make notebook     # executa a EDA e gera as figuras    (~2 min)
make test         # 25 testes
```

Tempos medidos em máquina com HD mecânico e conexão de ~4 MB/s.

### Reprodutibilidade

Rodar o pipeline duas vezes sobre os mesmos arquivos brutos produz os **17 CSVs byte a
byte idênticos** (amostragem com semente fixa, `SEED = 42` em `src/config.py`).

O `.hyper` é a única exceção, e por um motivo benigno: o formato embute estado interno,
então os bytes do arquivo mudam a cada escrita. O **conteúdo** é o mesmo — verificamos
tabela a tabela, e as nove são idênticas; apenas a ordem em que a tabela `amostra` volta
na leitura varia, porque Hyper é um banco de dados e não garante ordem de linha sem um
`ORDER BY` explícito. Isso não afeta o Tableau, que agrega. Se o `.hyper` aparecer como
modificado no `git status` sem você ter mudado nada, é isso.

### Saídas

```
outputs/tableau/
├── enem_tableau.hyper      # 9 tabelas — arraste este para o Tableau
├── enem_amostra.csv        # 200 mil linhas, 37 MB
└── agg_*.csv               # 8 tabelas agregadas
outputs/figures/            # 5 figuras da EDA
```

### Se o `.hyper` falhar

O `pantab`/`tableauhyperapi` só tem binário para x86-64 e arm64 em Linux, macOS e Windows.
Em plataforma sem suporte, `make export` **avisa em voz alta e segue gerando os CSVs** —
o pipeline não quebra, e o Tableau lê CSV sem problema. Neste ambiente o `.hyper` foi
gerado normalmente (5,4 MB, 9 tabelas).

---

## Estrutura

```
├── certs/                      # intermediário TLS que o INEP omite (ver decisão 6)
├── data/
│   ├── raw/                    # zips do INEP          (não versionado)
│   ├── interim/                # CSV extraído + Parquet (não versionado)
│   └── processed/              # tabelas agregadas
├── notebooks/01_eda_enem.ipynb # EDA com o raciocínio escrito
├── outputs/{figures,tableau}/
├── src/
│   ├── config.py               # caminhos, ESQUEMAS por edição, dicionários
│   ├── download.py             # download com retomada e TLS verificado (só stdlib)
│   ├── etl.py                  # leitura em blocos, limpeza, harmonização
│   ├── features.py             # decodificação e variáveis derivadas
│   ├── aggregate.py            # tabelas sobre a base completa
│   └── export_tableau.py       # amostragem, CSV e .hyper
├── tests/test_pipeline.py
├── TABLEAU_BLUEPRINT.md        # ← especificação do dashboard
└── README.md
```

`data/raw/` e `data/interim/` não são versionados: somam ~6 GB. `make download` os
reconstrói, e o download é idempotente — não rebaixa arquivo já íntegro.

---

## Fonte

Microdados do ENEM, edições 2022, 2023 e 2024 — INEP/MEC, dados abertos.
Portal: <https://www.gov.br/inep/pt-br/acesso-a-informacao/dados-abertos/microdados/enem>

Os arquivos são de uso público. Não contêm identificação pessoal: o número de inscrição é
mascarado pelo INEP e, segundo o dicionário, o mesmo `NU_INSCRICAO` em anos diferentes não
identifica o mesmo participante.

---

## Licença

Código e documentação sob [MIT](LICENSE).

Os microdados do ENEM são publicados pelo INEP/MEC como dados abertos e **não são cobertos
por esta licença** — ela se aplica apenas ao que há de autoral neste repositório. As
tabelas em `data/processed/` e `outputs/tableau/` são derivadas desses dados públicos e
seguem os termos de uso do INEP.
