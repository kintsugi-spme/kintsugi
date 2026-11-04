PDF = main.pdf
SRC = main.tex $(wildcard config/*.tex frontmatter/*.tex chapters/*.tex chapters/decisioni/*.tex appendices/*.tex)

SINTESI = main-sintesi.pdf
SRC_SINTESI = main-sintesi.tex $(wildcard config/*.tex frontmatter/frontespizio.tex sintesi/*.tex)

# Macro \parametro{chiave}, generate dai valori di ../config/parametri.yaml
PARAMETRI = config/parametri.tex

all: $(PDF) $(SINTESI)

sintesi: $(SINTESI)

parametri: $(PARAMETRI)

# Confronta i numeri marcati nei file Markdown con config/parametri.yaml
controlla:
	python3 scripts/parametri.py controlla

$(PARAMETRI): ../config/parametri.yaml scripts/parametri.py
	python3 scripts/parametri.py genera

$(PDF): $(SRC) $(PARAMETRI)
	latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex

$(SINTESI): $(SRC_SINTESI) $(PARAMETRI)
	latexmk -pdf -interaction=nonstopmode -halt-on-error main-sintesi.tex

clean:
	latexmk -C
	rm -f $(PARAMETRI)

.PHONY: all sintesi parametri controlla clean
