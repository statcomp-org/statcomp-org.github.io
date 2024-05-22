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

cv: jyanCV.pdf
	cp jyanCV.pdf ~/pdf/
	docker run -ti --rm -v ~/pdf:/pdf sergiomtzlosa/pdf2htmlex pdf2htmlEX --zoom 1.3 jyanCV.pdf jyanCV.html
	cp ~/pdf/jyanCV.html docs/

clean:
	rm -rf publications* *~
