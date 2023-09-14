all: publications
	@quarto render

publications: jyan.bib apa-cv.csl lua-refs.lua
	@quarto pandoc -L lua-refs.lua \
		jyan.bib --csl=apa-cv.csl \
		-V --toc=false \
		--to=markdown-citations \
		-o publications.qmd
	@Rscript highlight-author.R \
		"Yan, J." "publications.qmd"

clean:
	rm -rf publications* *~
