PY := .venv/bin/python

.PHONY: help venv download etl aggregate export notebook test all clean clean-raw

help:
	@echo "make venv       - cria a venv e instala dependências"
	@echo "make download   - baixa e extrai os microdados do INEP (~1,6 GB)"
	@echo "make etl        - CSV bruto -> Parquet harmonizado"
	@echo "make aggregate  - tabelas agregadas sobre a base completa"
	@echo "make export     - amostra + CSV + extract .hyper"
	@echo "make notebook   - executa a EDA e gera as figuras"
	@echo "make test       - roda os testes"
	@echo "make all        - pipeline completo"
	@echo "make clean      - remove saídas geradas (mantém os dados brutos)"

venv:
	python3 -m venv .venv
	$(PY) -m pip install --upgrade pip
	.venv/bin/pip install -r requirements.txt

# --insecure NÃO é usado: o intermediário TLS versionado em certs/ resolve a cadeia
# incompleta servida pelo INEP mantendo a verificação ativa. Ver README, decisão 6.
download:
	$(PY) src/download.py --anos 2022 2023 2024 --extrair

etl:
	$(PY) -m src.etl --anos 2022 2023 2024

aggregate:
	$(PY) -m src.aggregate

export:
	$(PY) -m src.export_tableau

notebook:
	.venv/bin/jupyter nbconvert --to notebook --execute --inplace \
		--ExecutePreprocessor.timeout=1800 notebooks/01_eda_enem.ipynb

test:
	$(PY) -m pytest tests/ -q

all: download etl aggregate export notebook test

clean:
	rm -f data/processed/*.csv outputs/tableau/* outputs/figures/*

# Separado do clean por ser destrutivo de verdade: apaga ~6 GB que levam minutos para
# rebaixar. Nunca encadeado em outro alvo.
clean-raw:
	rm -f data/raw/*.zip data/interim/*
