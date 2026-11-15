bucketName := statds.org

.PHONY: all publications cv-publications check-cv-publications cv clean

all: cv-publications
	@quarto render

publications: jyan.bib lcg-cv.csl lua-refs.lua
	@quarto pandoc -L lua-refs.lua \
		jyan.bib --csl=lcg-cv.csl \
		-V --toc=false \
		--to=markdown-citations \
		-o publications.qmd
	@Rscript group-publications.R \
		jyan.bib "publications.qmd"
	@Rscript highlight-author.R \
		"Yan, J." "publications.qmd"

cv-publications:
	@python3 scripts/generate-cv-publications.py

check-cv-publications:
	@python3 scripts/generate-cv-publications.py --check

cv: cv-publications
	latexmk -pdf jyanCV
	mkdir -p bindocs
	cp -p jyanCV.pdf bindocs/
	# cp jyanCV.pdf ~/pdf
	# docker run -ti --rm -v ~/pdf:/pdf sergiomtzlosa/pdf2htmlex pdf2htmlEX --zoom 1.3 jyanCV.pdf jyanCV.html
	# cp ~/pdf/jyanCV.html docs/

clean:
	rm -f publications.qmd cv-publications.tex *~


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
