MAIN = main.tex
ENGINE ?= xelatex

.PHONY: all clean watch

all:
	latexmk -$(ENGINE) -interaction=nonstopmode -halt-on-error $(MAIN)

watch:
	latexmk -$(ENGINE) -pvc -interaction=nonstopmode $(MAIN)

clean:
	latexmk -C $(MAIN)
