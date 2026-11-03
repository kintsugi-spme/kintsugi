PDF = main.pdf
SRC = main.tex $(wildcard config/*.tex frontmatter/*.tex chapters/*.tex chapters/decisioni/*.tex appendices/*.tex)

SINTESI = main-sintesi.pdf
SRC_SINTESI = main-sintesi.tex $(wildcard config/*.tex frontmatter/frontespizio.tex sintesi/*.tex)

all: $(PDF) $(SINTESI)

sintesi: $(SINTESI)

$(PDF): $(SRC)
	latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex

$(SINTESI): $(SRC_SINTESI)
	latexmk -pdf -interaction=nonstopmode -halt-on-error main-sintesi.tex

clean:
	latexmk -C

.PHONY: all sintesi clean
