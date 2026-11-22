# BuscaSUS

Busca de estabelecimentos de saúde do SUS (CNES) em linguagem do cidadão. Projeto acadêmico, UFMG.

O cidadão procura "postinho", "UPA" ou "CERSAM", e não pelo nome oficial do tipo de unidade.
O BuscaSUS traduz esses termos por meio de um tesauro e de uma taxonomia. A busca aceita
operadores lógicos e filtros, e mostra os resultados em um mapa com a opção "Perto de mim".

## Como rodar

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-etl.txt
.venv/bin/python -m etl.construir_base --csv ../cnes_estabelecimentos.csv --municipio 310620 --data-fonte DD/MM/AAAA
.venv/bin/uvicorn app.main:app --reload --no-access-log
```

Depois, abra http://localhost:8000. A base `data/buscasus.db` já vem no repositório, então o
segundo comando só é necessário para atualizar os dados.

Testes: `.venv/bin/pytest -q`

## Dados

- Fonte: conjunto [CNES – Estabelecimentos](https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/CNES/cnes_estabelecimentos_csv.zip)
  do Ministério da Saúde. Baixe o ZIP manualmente e passe o ZIP ou o CSV em `--csv`.
- Recorte da demo: Belo Horizonte (código IBGE `310620`). O município é um parâmetro do ETL.
- O ETL apaga e recria `data/buscasus.db` a cada execução. Ele mantém só as unidades ativas
  com atendimento ambulatorial SUS cujo tipo está no tesauro, e não armazena CNPJ nem e-mail.
- Base atual: 359 estabelecimentos (dados de 20/11/2026), todos com coordenadas.

| Categoria | Estabelecimentos |
| --- | ---: |
| Atenção básica | 154 |
| Atendimento especializado | 97 |
| Exames | 70 |
| Hospitais | 28 |
| Urgência e emergência | 9 |
| Farmácias | 1 |

## Como a busca funciona

O vocabulário fica em `vocabulario/tesauro.csv`. Cada linha é um termo preferido, com seus
termos não preferidos (sinônimos populares), o termo geral (`tg`, a categoria) e os termos
relacionados (`tr`).

| Consulta | O que acontece |
| --- | --- |
| `postinho no Barreiro` | "postinho" vira Centro de Saúde, e "barreiro" é procurado no nome e no endereço |
| `UPA` | Pronto Atendimento e, pelo termo relacionado, Pronto Socorro Geral |
| `posto` | Todos os tipos da categoria Atenção básica |
| `hospital NOT maternidade` | Hospitais sem centro obstétrico |
| `(caps OR policlínica) AND barreiro` | Operadores e parênteses |

- Os operadores `AND`, `OR` e `NOT` só valem quando escritos em maiúsculas. Sem operador,
  os termos são combinados com `AND`.
- Acentos e maiúsculas não importam: `saude` e `SAÚDE` dão o mesmo resultado.
- Uma expressão inválida, como `hospital (`, é tratada como busca simples e gera um aviso.
- Os filtros (categoria, tipo, característica e esfera) funcionam com ou sem texto de busca.
- A lista pode ser ordenada por relevância, por nome ou por distância.

## Estrutura

```
app/            site FastAPI + Jinja2 (rotas em main.py, busca em busca.py)
  templates/    páginas HTML renderizadas no servidor
  static/       CSS e mapa (Leaflet + OpenStreetMap)
etl/            construir_base.py: CSV do CNES → SQLite com índice FTS5
vocabulario/    tesauro.csv e ufs.csv
data/           buscasus.db, gerado pelo ETL e servido pelo site
tests/          testes da busca
```

## Rotas

| Rota | Conteúdo |
| --- | --- |
| `/` | Página inicial com campo de busca, exemplos e atalhos por categoria |
| `/busca` | Resultados com filtros, ordenação, mapa e "Perto de mim" |
| `/estabelecimento/{cnes}` | Detalhes de um estabelecimento |
| `/saude` | Health check (`ok`) |

## Deploy

O site roda no Render, no plano gratuito, a partir do `render.yaml`. O Render instala só
`requirements.txt` e serve a base já commitada. O plano gratuito hiberna quando fica sem
acesso, e a primeira visita depois disso pode levar cerca de um minuto.

O "Perto de mim" usa a geolocalização do navegador, que só funciona em HTTPS ou em
localhost. O servidor roda com `--no-access-log` para não registrar a localização dos
usuários.
