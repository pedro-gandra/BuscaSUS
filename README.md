# BuscaSUS

Busca de estabelecimentos de saúde do SUS (CNES) em linguagem do cidadão. Projeto acadêmico, UFMG.

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-etl.txt
.venv/bin/python -m etl.construir_base --csv ../cnes_estabelecimentos.csv --municipio 310620 --data-fonte DD/MM/AAAA
.venv/bin/uvicorn app.main:app --reload --no-access-log
```

Testes: `.venv/bin/pytest -q`
