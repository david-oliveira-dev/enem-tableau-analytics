# Blueprint do dashboard — ENEM 2022–2024

Guia de montagem no Tableau Public. Todos os campos citados existem nos arquivos de
`outputs/tableau/`; as fórmulas estão em sintaxe Tableau, prontas para colar.

> **Antes de começar:** o Tableau lê tanto `enem_tableau.hyper` (um arquivo, nove tabelas)
> quanto os `.csv` soltos. O `.hyper` é a opção recomendada — abre mais rápido e mantém os
> tipos. No Tableau Public: *Conectar → Mais → Arquivo estatístico* não serve; use
> **Conectar → Para um arquivo → Mais → selecione o `.hyper`**.

---

## 1. Fontes de dados e quando usar cada uma

O ponto que mais causa erro neste projeto: **há duas granularidades, e trocá-las produz
números errados com aparência correta.**

| Fonte | Granularidade | Use para | **Nunca** use para |
|---|---|---|---|
| `agg_uf`, `agg_rede`, `agg_renda`, `agg_area`, `agg_faixas`, `agg_perfil`, `agg_uf_rede`, `agg_renda_rede` | Já agregada, sobre os **8,0 milhões** de participantes | Mapa, KPIs, séries temporais, barras | Boxplot, histograma, qualquer distribuição |
| `amostra` | 1 linha por participante, **200 mil** linhas (2,5% de cada UF) | Boxplot, histograma, scatter, densidade | Ler valor exato de uma UF pequena |

**Regra prática:** se o gráfico mostra um *número* para o usuário ler, vem de `agg_*`. Se
mostra uma *forma* (dispersão, cauda, mediana visual), vem de `amostra`.

Nas tabelas `agg_*`, as colunas `nota_media_*` **já são médias**. Ao arrastar para a
visualização, o Tableau aplica `SUM()` por padrão — troque para `AVG()`, ou melhor, use a
média ponderada da seção 2, porque a média de médias entre UFs de tamanhos diferentes
está errada.

---

## 2. Campos calculados

### 2.1 Obrigatórios

**`Media Ponderada`** — em qualquer tabela `agg_*` com `n_participantes`.
Média simples entre UFs daria a Roraima o mesmo peso de São Paulo.

```
SUM([Nota Media Geral] * [N Participantes]) / SUM([N Participantes])
```

**`Gap Privada Publica`** — a métrica-título do dashboard. Sobre `agg_rede` ou `agg_uf_rede`:

```
SUM(IF [Rede] = "Privada" THEN [Nota Media Geral] * [N Participantes] END)
  / SUM(IF [Rede] = "Privada" THEN [N Participantes] END)
-
SUM(IF [Rede] = "Publica" THEN [Nota Media Geral] * [N Participantes] END)
  / SUM(IF [Rede] = "Publica" THEN [N Participantes] END)
```

> Atenção ao acento: no arquivo o valor é `Pública`, com acento. Copie o texto do próprio
> campo em vez de digitar, senão a condição nunca casa e o resultado sai nulo.

**`Rotulo Gap`** — formatação com sinal, para o KPI:

```
IF [Gap Privada Publica] > 0
THEN "+" + STR(ROUND([Gap Privada Publica], 1)) + " pts"
ELSE STR(ROUND([Gap Privada Publica], 1)) + " pts"
END
```

**`Cor Desvio Nacional`** — dá cor ao mapa. Já vem calculado como `desvio_vs_nacional`
em `agg_uf`; este campo só existe para fixar a escala (ver parâmetro `p_Escala_Mapa`):

```
MIN(MAX([Desvio Vs Nacional], -[p_Escala_Mapa]), [p_Escala_Mapa])
```

### 2.2 Para os sheets de distribuição (fonte `amostra`)

**`Chance Quintil Superior`** — o número que abre o dashboard, em percentual:

```
SUM(IF [Quintil Desempenho] = "Q5 (mais alto)" THEN 1 ELSE 0 END)
/ COUNT([Nota Media Geral])
```

**`Razao de Acesso ao Topo`** — quantas vezes a rede privada supera a pública em chance
de chegar ao quintil superior (deu 4,2 em 2023):

```
{ FIXED [Ano] : SUM(IF [Rede] = "Privada" AND [Quintil Desempenho] = "Q5 (mais alto)" THEN 1 END) }
/ { FIXED [Ano] : SUM(IF [Rede] = "Privada" THEN 1 END) }
/
(
{ FIXED [Ano] : SUM(IF [Rede] = "Pública" AND [Quintil Desempenho] = "Q5 (mais alto)" THEN 1 END) }
/ { FIXED [Ano] : SUM(IF [Rede] = "Pública" THEN 1 END) }
)
```

**`Nota Selecionada`** — permite ao usuário trocar a área exibida sem duplicar sheets.
Depende do parâmetro `p_Area` (seção 3):

```
CASE [p_Area]
  WHEN "Média geral"          THEN [Nota Media Geral]
  WHEN "Média das objetivas"  THEN [Nota Media Objetivas]
  WHEN "Ciências da Natureza" THEN [Nota Cn]
  WHEN "Ciências Humanas"     THEN [Nota Ch]
  WHEN "Linguagens e Códigos" THEN [Nota Lc]
  WHEN "Matemática"           THEN [Nota Mt]
  WHEN "Redação"              THEN [Nota Redacao]
END
```

**`Acima do Corte`** — percentual acima de uma nota definida pelo usuário:

```
SUM(IF [Nota Selecionada] >= [p_Nota_Corte] THEN 1 ELSE 0 END) / COUNT([Nota Media Geral])
```

**`Faixa Etaria Ordenada`** — a faixa etária vem como texto e o Tableau ordena
alfabeticamente ("17 anos" depois de "Menor de 17 anos"). Este campo dá a ordem certa:

```
CASE [Faixa Etaria Desc]
  WHEN "Menor de 17 anos" THEN 1
  WHEN "17 anos" THEN 2
  WHEN "18 anos" THEN 3
  WHEN "19 anos" THEN 4
  WHEN "20 anos" THEN 5
  ELSE 6
END
```

### 2.3 Aviso de cobertura (recomendado)

A cobertura da variável de rede saltou de 26,9% (2023) para 39,9% (2024), o que infla
parte do gap de 2024. Este campo mostra a ressalva **no próprio gráfico**, em vez de
escondê-la no README:

```
IF [Ano] = 2024
THEN "⚠ Cobertura da variável de rede subiu de 26,9% para 39,9% em 2024; parte do aumento do gap é composição da base."
ELSE ""
END
```

Coloque em *Tooltip* no sheet S2 e em *Detalhe* no KPI do gap.

---

## 3. Parâmetros

| Parâmetro | Tipo | Valores | Para quê |
|---|---|---|---|
| `p_Ano` | Inteiro, lista | 2022, 2023, 2024 | Edição exibida nos sheets de ano único |
| `p_Area` | String, lista | Média geral; Média das objetivas; Ciências da Natureza; Ciências Humanas; Linguagens e Códigos; Matemática; Redação | Alimenta `Nota Selecionada` |
| `p_Nota_Corte` | Float, deslizante | 300 a 900, passo 10, padrão 600 | Alimenta `Acima do Corte` |
| `p_Escala_Mapa` | Float, deslizante | 10 a 60, passo 5, **padrão 45** | **Fixa a escala de cor do mapa** |

> **`p_Escala_Mapa` não é opcional.** A amplitude entre UFs é praticamente constante nas
> três edições (63,6 / 64,8 / 65,2 pontos). Se a escala de cor for recalculada por ano — o
> padrão do Tableau — o mapa parecerá mudar de 2022 para 2024 enquanto os dados dizem que
> nada mudou. Escala fixa é o que impede o dashboard de inventar uma tendência.

---

## 4. Filtros

Aplicar como **filtros de contexto** (clique direito → *Adicionar ao contexto*) para que os
cálculos LOD `{FIXED}` respeitem a seleção:

| Filtro | Campo | Modo | Observação |
|---|---|---|---|
| Edição | `Ano` | Lista múltipla | Padrão: todos |
| Região | `Regiao` | Lista múltipla | Hierarquia com UF |
| UF | `Uf Nome` | Lista múltipla | Dependente de Região |
| Rede | `Rede` | Lista múltipla | Padrão: Pública e Privada, **excluir Nulo** |
| Faixa de renda | `Renda Grupo` | Lista múltipla | Só afeta sheets de 2022–2023 |
| Sexo | `Sexo Desc` | Lista múltipla | Só afeta sheets de 2022–2023 |

**Filtro obrigatório em qualquer sheet socioeconômico:** `Edicao Completa = Verdadeiro`.
Sem ele, as 74.629 linhas de 2024 entram com renda e sexo nulos e aparecem como uma
categoria "Null" nos gráficos.

**Hierarquia:** arraste `Regiao` sobre `Uf Nome` para criar `Geografia`, permitindo
drill-down no mapa.

---

## 5. Sheets

### S1 — KPIs (fonte: `agg_rede` + `amostra`)
Quatro tiles em *Texto*, lado a lado:

1. **Nota média nacional** — `Media Ponderada`, formato `0,0`
2. **Gap privada − pública** — `Rotulo Gap`, cor `#C1666B`
3. **Razão de acesso ao topo** — `Razao de Acesso ao Topo`, formato `0,0` + sufixo `×`
4. **Participantes analisados** — `SUM([N Participantes])`, formato `0,0 mi`

### S2 — Mapa coroplético: nota média por UF (fonte: `agg_uf`)
- Marca: **Mapa preenchido**. `Uf` no *Detalhe*, definido como Função geográfica → Estado.
  Se o Tableau não reconhecer, use `Uf Nome` (nomes por extenso já vêm prontos por isso).
- Cor: `Cor Desvio Nacional`, paleta **divergente vermelho–azul**, centro em 0, limites
  fixos em −`p_Escala_Mapa` e +`p_Escala_Mapa`.
- Tooltip: UF, região, `nota_media_geral`, `desvio_vs_nacional`, `n_participantes`.
- Filtro: `p_Ano`.

### S3 — Barras por área de conhecimento (fonte: `agg_area`)
- Linhas: `Area` (ordenar decrescente por `Media Ponderada`).
- Colunas: `Media Ponderada`. Cor: `Rede`.
- Barras lado a lado, não empilhadas — a comparação é entre redes, e empilhar somaria
  notas, o que não significa nada.
- Rótulo: diferença entre redes por área. Redação (+173) contra Linguagens (+56) é o
  contraste que este sheet existe para mostrar.

### S4 — Boxplot pública × privada (fonte: `amostra`)
- Colunas: `Rede`. Linhas: `Nota Selecionada`.
- Marca *Circle*, depois **Analytics → Box Plot**.
- `Ano` em *Colunas* antes de `Rede` para ver as três edições lado a lado.
- Filtro: `Rede` ≠ Nulo.
- **Este sheet exige a amostra** — a caixa precisa dos quartis individuais, e as tabelas
  `agg_*` não os têm.

### S5 — Scatter renda × nota (fonte: `agg_renda` para a linha, `amostra` para a nuvem)
- Colunas: `renda_sm_ponto_medio` (contínuo). Linhas: `Media Ponderada`.
- Tamanho da marca: `n_participantes`. Cor: `Ano`.
- **Analytics → Linha de tendência → Linear**, com R² exibido.
- Filtro: `Ano` em 2022 e 2023 apenas (2024 não tem renda).
- Rótulo no eixo X: "Renda familiar (salários mínimos, ponto médio da faixa)" — a unidade
  é SM e não reais justamente para que 2022 e 2023 sejam comparáveis apesar do reajuste.

### S6 — Barras empilhadas: quintil por rede e por renda (fonte: `amostra`)
- Linhas: `Rede`, depois `Renda Grupo` num segundo painel.
- Colunas: `CNTD` percentual do total da tabela (*Análise rápida → Percentual de → Tabela*).
- Cor: `Quintil Desempenho`, paleta sequencial de 5 tons.
- É o sheet que traduz o gap em chance de acesso: 50,5% contra 12,1% no quintil superior.

### S7 — Série temporal do gap (fonte: `agg_rede`)
- Colunas: `Ano`. Linhas: `Gap Privada Publica`.
- Marca: linha com rótulo em cada ponto (89,5 → 97,7 → 103,3).
- Tooltip: incluir o campo `Aviso Cobertura` da seção 2.3.

### S8 — Tabela de detalhe por UF (fonte: `agg_uf` + `agg_uf_rede`)
- Texto em tabela cruzada: UF nas linhas; nota média, mediana, desvio-padrão e
  n_participantes nas colunas; `Ano` como coluna aninhada.
- Serve de "mostre-me os números" para quem desconfia do mapa — e evita que alguém tire
  valor exato lendo pixel de gráfico.

---

## 6. Layout do dashboard

Tamanho: **1200 × 2000 px**, fixo (o Tableau Public renderiza melhor em largura fixa que
em automático).

```
┌──────────────────────────────────────────────────────────────┐
│  TÍTULO: ENEM 2022–2024 — onde a desigualdade se concentra   │
│  subtítulo: 8,0 mi de participantes · fonte INEP · microdados │
├──────────────────────────────────────────────────────────────┤
│  S1  [ Nota média ] [ Gap ] [ Razão topo ] [ Participantes ] │  140 px
├───────────────────────────────┬──────────────────────────────┤
│                               │                              │
│  S2  Mapa por UF              │  S3  Barras por área         │  480 px
│                               │                              │
├───────────────────────────────┴──────────────────────────────┤
│  S7  Série do gap (largura total, altura baixa)              │  220 px
├───────────────────────────────┬──────────────────────────────┤
│  S4  Boxplot rede             │  S5  Scatter renda × nota    │  420 px
├───────────────────────────────┴──────────────────────────────┤
│  S6  Quintis por rede e renda (largura total)                │  380 px
├──────────────────────────────────────────────────────────────┤
│  S8  Tabela por UF (contêiner recolhível)                    │  260 px
├──────────────────────────────────────────────────────────────┤
│  RODAPÉ: limitações + link do repositório + data dos dados   │  100 px
└──────────────────────────────────────────────────────────────┘
```

Barra lateral de filtros: contêiner flutuante à direita, `p_Ano`, `p_Area`, Região, UF,
Rede. Recolhida por padrão (*Mostrar botão de exibir/ocultar*).

**Rodapé — texto sugerido, não omita:**

> Dados: microdados do ENEM (INEP), edições 2022–2024. Considera apenas participantes
> presentes nos dois dias de prova. A rede de ensino vem do pareamento com o Censo Escolar
> e cobre 26,9%–39,9% dos participantes conforme a edição. Recortes de renda e sexo não
> estão disponíveis em 2024: o INEP publicou perfil e notas em bases sem chave de ligação.

---

## 7. Paleta

Divergente para o mapa, categórica para o resto. Testada para daltonismo
(deuteranopia) — o par vermelho/azul-petróleo mantém contraste em escala de cinza.

| Uso | Hex | Onde |
|---|---|---|
| Rede privada | `#C1666B` | S3, S4, S7 |
| Rede pública | `#48A9A6` | S3, S4, S7 |
| Destaque / KPI principal | `#4C5B7D` | S1, S7 |
| Acento (alertas, Redação) | `#E9A03B` | rótulos de destaque |
| Neutro / grade | `#CBD2D9` | linhas de referência |
| Texto | `#2E3440` | títulos e rótulos |
| Fundo | `#FFFFFF` | dashboard |

**Mapa (divergente, centro em 0):**
`#B2182B` → `#EF8A62` → `#F7F7F7` → `#67A9CF` → `#2166AC`
(vermelho = abaixo da média nacional, azul = acima)

**Quintis (sequencial, 5 tons)** — a mesma usada nas figuras do notebook:
`#C1666B` · `#E0A96D` · `#CBD2D9` · `#7EA8BE` · `#4C5B7D`

**Regiões:**
Norte `#C1666B` · Nordeste `#E9A03B` · Centro-Oeste `#8FBF62` · Sudeste `#4C5B7D` · Sul `#48A9A6`

---

## 8. Ordenação manual de campos

O `.hyper` não preserva ordem de categórica (o formato não tem esse conceito). Estes
quatro campos precisam de ordenação manual em *Clique direito → Padrão → Classificar →
Manual*:

**`Renda Grupo`**
`Sem renda` → `Até 1 SM` → `1 a 2 SM` → `2 a 3 SM` → `3 a 5 SM` → `5 a 10 SM` → `Acima de 10 SM`

**`Faixa Nota`**
`Até 400` → `400 a 500` → `500 a 600` → `600 a 700` → `Acima de 700`

**`Quintil Desempenho`**
`Q1 (mais baixo)` → `Q2` → `Q3` → `Q4` → `Q5 (mais alto)`

**`Faixa Etaria Desc`** — use `Faixa Etaria Ordenada` (seção 2.2) como chave de
classificação em vez de ordenar 20 categorias na mão.

---

## 9. Checklist antes de publicar

- [ ] `p_Escala_Mapa` fixo — trocar de ano não deve alterar a escala de cor
- [ ] Todo campo `nota_media_*` usa `AVG()` ou `Media Ponderada`, nunca `SUM()`
- [ ] Sheets socioeconômicos filtram `Edicao Completa = Verdadeiro`
- [ ] Filtro `Rede` exclui Nulo em todos os sheets que usam rede
- [ ] Nenhum sheet de distribuição (S4, S5, S6) puxa de tabela `agg_*`
- [ ] Nenhum KPI ou mapa puxa da `amostra`
- [ ] Tooltip do gap de 2024 traz o aviso de cobertura
- [ ] Rodapé com limitações preenchido
- [ ] Filtros aplicados como filtros de **contexto** onde há `{FIXED}`
