# BuscaSUS — MVP

Site acadêmico (UFMG) de busca de estabelecimentos de saúde do SUS a partir do CNES.
O diferencial é entender a linguagem do cidadão ("postinho", "UPA", "CERSAM") por meio de
um tesauro e de uma taxonomia, e recuperar com filtros, operadores lógicos e mapa.

- Relatório completo (contexto e regras):
  https://docs.google.com/document/d/1g8WuykkLThFT62DH5of_BZh5ndx5SBLN7YnQi_qQjCo/edit
  Leia pelo Google Drive em texto (`read_file_content`); a leitura completa pelo
  conector do Google Docs passa de 1,5 milhão de caracteres. As seções que importam
  para o código são 3.1, 3.2, 3.3 e 4, e o Apêndice A (tesauro).
- **O MVP implementa só uma parte do relatório.** Este arquivo define o que entra.
  A gestão arquivística (seção 3.4) não entra no código.
- Prazo: pitch com demo ao vivo em 23/11/2026. Prefira o simples que funciona.

## O que importa no MVP

1. A base é construída a partir do CSV do CNES com um único comando, sempre que preciso.
2. As buscas funcionam pelo celular: busca simples com tesauro, operadores e filtros.
3. Mapa com os resultados e "Perto de mim".

Todo o resto é secundário. Se o tempo apertar, corte na ordem da seção "Se faltar tempo".

## Stack (decidida)

| Parte | Escolha |
| --- | --- |
| ETL | Python 3.12, pandas (só no ETL) |
| Base | SQLite, um arquivo `data/buscasus.db`, busca textual com FTS5 |
| Site | FastAPI + Jinja2, HTML renderizado no servidor, JS mínimo, CSS próprio simples |
| Mapa | Leaflet + OpenStreetMap (CDN, sem chave de API) |
| Deploy | Render, plano gratuito, a partir do GitHub (`render.yaml`) |
| Recorte da demo | Belo Horizonte (código IBGE `310620`); o recorte é parâmetro do ETL |

Sem React, sem ORM, sem Elasticsearch. `sqlite3` da biblioteca padrão basta.

## Estrutura do repositório

```
buscasus/
  CLAUDE.md
  README.md                  # como rodar em 3 comandos
  requirements.txt           # site: fastapi, uvicorn, jinja2
  requirements-etl.txt       # ETL: pandas
  render.yaml
  vocabulario/
    tesauro.csv              # já existe; Apêndice A do relatório
  etl/
    construir_base.py        # python -m etl.construir_base --csv <zip ou csv> --municipio 310620
  app/
    main.py                  # rotas FastAPI
    busca.py                 # tratamento da consulta e expressão FTS5
    templates/               # base.html, inicio.html, resultados.html, estabelecimento.html
    static/                  # estilo.css, mapa.js
  data/
    buscasus.db              # gerado pelo ETL e commitado: é o que o Render serve
  tests/
    test_busca.py
```

`.gitignore`: `*.zip`, `*.csv` fora de `vocabulario/`, `.venv/`, `__pycache__/`.

## Construção da base (`etl/construir_base.py`)

Um script só, que apaga e recria `data/buscasus.db` a cada execução.

- Entrada: o ZIP ou o CSV do conjunto "CNES – Estabelecimentos"
  (`https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/CNES/cnes_estabelecimentos_csv.zip`),
  baixado manualmente e passado por `--csv`. Parâmetros: `--municipio` (padrão `310620`)
  e `--data-fonte` (data de atualização dos dados, para o rodapé).
- Leitura: separador `;`, **todas as colunas como texto**
  (`dtype=str, keep_default_na=False`), UTF-8 com fallback para Latin-1.
  Textos vêm em maiúsculas e sem acento.
- Colunas usadas: `CO_CNES, NO_FANTASIA, NO_RAZAO_SOCIAL, CO_IBGE, CO_CEP,
  NO_LOGRADOURO, NU_ENDERECO, NO_BAIRRO, NU_LATITUDE, NU_LONGITUDE, TP_UNIDADE,
  DS_ESFERA_ADMINISTRATIVA, DS_TURNO_ATENDIMENTO, CO_AMBULATORIAL_SUS,
  ST_CENTRO_OBSTETRICO, ST_ATEND_HOSPITALAR, CO_MOTIVO_DESAB, NU_TELEFONE`.
  Confira os nomes no cabeçalho real.
- Limpeza (seção 3.1): `strip()`; vazio vira `None`; CNES com zfill(7); `TP_UNIDADE`
  com zfill(2); CEP com 8 dígitos; latitude e longitude para float (inválido vira `None`);
  `ST_*` "1.0"/"0.0" para 1/0; `CO_AMBULATORIAL_SUS` SIM/NAO para 1/0.
- Seleção: município = parâmetro; `CO_MOTIVO_DESAB` vazio; `CO_AMBULATORIAL_SUS = 1`;
  `TP_UNIDADE` presente no `tesauro.csv` (coluna `tipo_cnes`); deduplicar por CNES.
- Exibição: nome e endereço em caixa mista, preservando siglas (UPA, UBS, CAPS, CERSAM,
  SUS, CEO).
- Não armazenar CNPJ nem e-mail.
- Ao final, imprimir: lidos, selecionados, sem coordenadas e contagem por tipo.

## Indexação (seção 3.2.3)

Cada estabelecimento recebe termos (tabela `assunto`):

- termo preferido do seu tipo (linha do `tesauro.csv` com o mesmo `tipo_cnes`) e a
  categoria dele (coluna `tg`);
- "Atendimento 24 horas" se `DS_TURNO_ATENDIMENTO` indicar atendimento contínuo
  (confira os valores reais);
- "Maternidade" se `ST_CENTRO_OBSTETRICO = 1`;
- "Internação" se `ST_ATEND_HOSPITALAR = 1`.

## Esquema SQLite

Colunas nomeadas pelo perfil Dublin Core da seção 3.3 (só nomes, sem trabalho extra).

```sql
CREATE TABLE estabelecimento (
  identifier TEXT PRIMARY KEY,    -- CNES 7 dígitos
  title TEXT NOT NULL,            -- nome
  alternative TEXT,               -- razão social
  type TEXT NOT NULL,             -- termo preferido do tipo
  tipo_cnes TEXT NOT NULL,
  categoria TEXT NOT NULL,
  logradouro TEXT, numero TEXT, bairro TEXT, cep TEXT,
  municipio TEXT, municipio_nome TEXT, uf TEXT,
  latitude REAL, longitude REAL,
  turno TEXT, esfera TEXT, telefone TEXT
);
CREATE TABLE assunto (identifier TEXT, termo TEXT NOT NULL);
CREATE TABLE info (chave TEXT PRIMARY KEY, valor TEXT);   -- fonte, data_fonte
CREATE VIRTUAL TABLE busca USING fts5(
  identifier UNINDEXED, nome, termos, endereco,
  tokenize = 'unicode61 remove_diacritics 2'
);
```

`termos` em `busca` recebe os termos de `assunto` mais os não preferidos de cada um
(do tesauro). Assim "upa" também casa direto no índice.

## Busca (seções 3.2.2 e 4)

`app/busca.py` recebe o texto e devolve a expressão FTS5 e a interpretação para a tela.

1. Normalizar (minúsculas, sem acento, sem pontuação exceto parênteses e aspas).
2. Separar `AND`, `OR`, `NOT` (só em **maiúsculas** no texto original) e parênteses.
3. Remover palavras vazias: de, da, do, das, dos, no, na, nos, nas, em, a, o, e.
4. Reconhecer termos do tesauro pela correspondência mais longa primeiro
   ("posto de saúde" antes de "posto").
5. Mapear: não preferido vira o preferido; incluir os TR; termo de categoria vira todos
   os tipos com aquele `tg`. Ex.: `termos:("centro de saude/unidade basica" OR "posto de saude")`.
6. Palavras não reconhecidas: `{nome endereco}:palavra`.
7. Sem operador explícito, usar `AND`.
8. Expressão inválida: ignorar operadores, tratar como busca simples e mostrar aviso.
9. Devolver "você buscou X → mostrando Y" para exibir acima dos resultados.

SQL: `WHERE busca MATCH ? ORDER BY bm25(busca, 0.0, 10.0, 5.0, 1.0)` (um peso por coluna,
incluindo `identifier`). Sempre parâmetros `?`, nunca interpolar texto no SQL.
Testado: a sintaxe `termos:(... OR ...) AND palavra` e `{nome endereco}:palavra`
funciona no FTS5.

**Filtros** (query string de `/busca`, funcionam sem `q`): `categoria`, `tipo`,
`caracteristica`, `esfera`. Valores do mesmo filtro com OR; filtros diferentes com AND.

**Ordenação**: relevância (padrão; sem `q`, por nome), nome, distância (com `lat` e `lon`;
Haversine em Python).

## Páginas

| Rota | Conteúdo |
| --- | --- |
| `GET /` | Campo de busca, exemplos clicáveis ("postinho", "UPA", "CERSAM", "hospital NOT maternidade") e atalhos por categoria |
| `GET /busca` | Aviso de interpretação, filtros, lista (nome, tipo, categoria, endereço, bairro), ordenação, mapa com os resultados que têm coordenadas, botão "Perto de mim" |
| `GET /estabelecimento/{cnes}` | Detalhes (nome, tipo, categoria, endereço, telefone, turno, esfera, termos), mapa pequeno |
| `GET /saude` | Responde `ok` (health check do Render) |

Rodapé de todas as páginas: "Fonte: CNES – Estabelecimentos, Ministério da Saúde.
Dados de DD/MM/AAAA." (tabela `info`) e "Projeto acadêmico, sem vínculo com o Ministério
da Saúde. Estar no cadastro não garante atendimento ou vaga."

**Celular primeiro**: projete para 360 px de largura. Filtros recolhíveis acima da lista
(`<details>`), mapa com altura fixa (~45% da tela) acima ou abaixo da lista, alvos de toque
grandes, rótulos em todos os campos. Teste no modo responsivo do navegador.

**Mapa e "Perto de mim"**: Leaflet com tiles do OpenStreetMap e atribuição visível.
Marcadores com popup (nome + link para detalhes). O botão usa `navigator.geolocation`
e recarrega `/busca` com `lat`, `lon` e `ordem=distancia`. Geolocalização só funciona em
HTTPS ou localhost (o Render já serve HTTPS). Não registrar `lat`/`lon` em log:
iniciar o uvicorn com `--no-access-log`.

## Deploy (Render)

`render.yaml`: web service Python; build `pip install -r requirements.txt`; start
`uvicorn app.main:app --host 0.0.0.0 --port $PORT --no-access-log`; health check `/saude`.
O ETL roda no notebook e `data/buscasus.db` é commitado. O plano gratuito hiberna:
abrir o site alguns minutos antes do pitch.

## Fora do MVP (não implementar)

Gestão arquivística (lotes, hash, pastas de originais, logs de carga, plano de
classificação), página ou endpoint JSON de metadados, formulário separado de busca
avançada (os operadores funcionam na própria caixa de busca), contagem por opção nos
filtros, outros municípios, atualização automática, login, IA generativa,
autocompletar, exportação.

## Ordem de trabalho

1. `etl/construir_base.py` e a base de BH; conferir a contagem por tipo.
2. `app/busca.py` com `tests/test_busca.py` passando.
3. Página de resultados com filtros e lista, já responsiva.
4. Mapa e "Perto de mim".
5. Página de detalhes e página inicial.
6. Deploy no Render e teste no celular pela URL pública.

## Se faltar tempo, corte nesta ordem

Ordenação por nome → filtro de esfera → mapa pequeno na página de detalhes →
aviso de expressão inválida (mantenha só a busca sem erro 500).

## Consultas de aceitação

| Consulta | Esperado |
| --- | --- |
| `postinho no Barreiro` | Centros de saúde com "barreiro" no nome ou endereço; aviso mostra o mapeamento |
| `UPA` | Pronto Atendimento e, pelo TR, Pronto Socorro Geral |
| `cersam` | Centros de Atenção Psicossocial |
| `posto` | Todos os tipos da categoria Atenção básica |
| `hospital NOT maternidade` | Hospitais sem o termo Maternidade |
| `(caps OR policlínica) AND barreiro` | CAPS ou policlínicas com "barreiro" |
| `saude` e `SAÚDE` | Mesmo resultado |
| `hospital (` | Sem erro 500 |
| Sem `q`, `categoria=Urgência e emergência&caracteristica=Atendimento 24 horas` | Urgência 24 h em BH |
| "Perto de mim" no celular | Lista ordenada por distância e mapa centrado no usuário |

## Pontos a conferir nos dados reais

- Códigos e nomes de `TP_UNIDADE` no `tesauro.csv` foram escritos de memória; conferir
  com os valores do CSV ou `https://apidadosabertos.saude.gov.br/cnes/tipounidades`.
- `CO_MOTIVO_DESAB` preenchido = desabilitado (confirmar).
- Valores reais de `DS_TURNO_ATENDIMENTO` para identificar o atendimento 24 h.

Se algum desses pontos mudar uma regra do relatório, avise o grupo em vez de contornar.
