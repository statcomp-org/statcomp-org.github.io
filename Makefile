bucketName := statds.org

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

cv:
	latexmk -pdf jyanCV
	cp -p jyanCV.pdf bindocs/
	# cp jyanCV.pdf ~/pdf
	# docker run -ti --rm -v ~/pdf:/pdf sergiomtzlosa/pdf2htmlex pdf2htmlEX --zoom 1.3 jyanCV.pdf jyanCV.html
	# cp ~/pdf/jyanCV.html docs/

clean:
	rm -rf publications* *~


# push a local media copy (under photos/) to the remote bucket
.PHONY: push
push:
	aws s3 sync --profile statds bindocs/ s3://$(bucketName)/doc/bindocs --delete \
	--exclude ".DS_Store" \
	--exclude "**/.DS_Store"

# pull a local media copy from the remote bucket to static/media/
.PHONY: pull
pull:
	aws s3 sync --profile statds s3://$(bucketName)/doc/bindocs bindocs/ --delete \
	--exclude ".DS_Store" \
	--exclude "**/.DS_Store"
