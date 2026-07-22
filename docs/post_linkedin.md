# Post para LinkedIn

**Imagem:** `outputs/figures/post_linkedin.png` (1200×1200)
**Link:** https://github.com/david-oliveira-dev/enem-tableau-analytics

---

## Legenda

Passei os últimos dias com 4,7 GB de microdados do ENEM abertos no editor, e o achado
que menos esperava não foi sobre nota — foi sobre o próprio dado.

Comecei querendo comparar três edições (2022, 2023 e 2024). No meio do caminho, ao
conferir o dicionário de variáveis, descobri duas coisas:

→ A variável Q006 era "renda mensal da família" até 2023. Em 2024 ela virou "Você possui
renda?", e a renda familiar foi para a Q007.

→ Em 2024 o INEP passou a publicar perfil e notas em duas bases separadas, sem chave de
ligação. O dicionário é explícito: "não é possível utilizá-la para relacionar as duas
bases".

A segunda mudança significa que, em 2024, cruzar renda com nota é estruturalmente
impossível. A primeira é mais traiçoeira: se eu tivesse assumido que Q006 continuava
sendo renda, teria produzido um gráfico de renda × nota perfeitamente plausível — e
completamente errado. Nenhum teste genérico pegaria isso. Nenhuma revisão de código
pegaria isso. Só ler o dicionário pega.

Foi a lição mais útil do projeto: em dado público, o esquema é uma dependência externa
que muda sem aviso. Passei a tratar o mapeamento de colunas como configuração explícita
por edição, com o pipeline falhando alto quando encontra um ano que não conhece — em vez
de adivinhar e seguir em frente.

Sobre o que os dados dizem, com 8 milhões de participantes analisados:

• A diferença entre rede privada e pública cresceu nas três edições: 89 → 98 → 103 pontos

• Ela não se distribui igualmente. Em Redação são 173 pontos; em Linguagens, 56. Redação
e Matemática são justamente as áreas que dependem de correção individual e repetida —
o insumo que escala pior em turma lotada

• A nota sobe de forma quase linear com a renda, sem platô: 480 pontos na faixa sem renda
contra 637 acima de 10 salários mínimos

• A desigualdade entre estados não se moveu: 63,6 / 64,8 / 65,2 pontos de amplitude nas
três edições

Traduzindo em acesso, que é o que decide vaga: 50,5% dos alunos de escola privada chegam
ao quintil superior, contra 12,1% da rede pública.

Uma ressalva que faço questão de deixar no gráfico e não escondida no rodapé: a cobertura
da variável de rede saltou de 26,9% para 39,9% em 2024. Mudou quem está dentro da
comparação, então parte do aumento do gap naquele ano é composição da base, não queda de
desempenho. A tendência de 2022 para 2023 é sólida; a de 2024 eu leio como limite superior.

O repositório tem o pipeline completo (download com verificação de integridade, ETL em
blocos, feature engineering, agregações e export para .hyper), o notebook com o raciocínio
escrito e um blueprint com as fórmulas em sintaxe Tableau para montar o dashboard.

Link nos comentários. Feedback é muito bem-vindo — principalmente de quem já trabalhou
com microdados do INEP e passou por essas mudanças de esquema.

---

## Primeiro comentário (o link vai aqui, não no corpo do post)

Repositório: https://github.com/david-oliveira-dev/enem-tableau-analytics

Fonte dos dados: microdados do ENEM, INEP/MEC — dados abertos
https://www.gov.br/inep/pt-br/acesso-a-informacao/dados-abertos/microdados/enem

---

## Tags

```
#ENEM #DadosAbertos #DataAnalytics #Python #Pandas #Tableau #DataVisualization
#AnaliseDeDados #INEP #BusinessIntelligence #EducacaoNoBrasil #DataEngineering
```

**Se preferir menos tags** (o LinkedIn favorece 3 a 5):

```
#DadosAbertos #Python #Tableau #AnaliseDeDados #ENEM
```

---

## Notas de publicação

- **Link no primeiro comentário, não no corpo.** O LinkedIn reduz o alcance de posts com
  link externo no texto principal.
- **As primeiras duas linhas são o que aparece antes do "ver mais"** — por isso o post
  abre com o achado inesperado, não com "fiz um projeto".
- **Melhor horário:** terça a quinta, entre 8h e 10h.
- A imagem é quadrada (1200×1200), formato que ocupa mais altura no feed que o 1200×628.
