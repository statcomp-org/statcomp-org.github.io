all: publications
	@quarto render

publications: pubs.bib apa-cv.csl lua-refs.lua
	@quarto pandoc -L lua-refs.lua \
		pubs.bib --csl=apa-cv.csl \
		-V --toc=false \
		--to=markdown-citations \
		-o publications.qmd
	@Rscript highlight-author.R \
		"Hernandez, K." "publications.qmd"

clean:
	rm -rf publications* *~
