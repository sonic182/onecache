# Minimal makefile for Sphinx documentation and some more project commands
#

# You can set these variables from the command line, and also
# from the environment for the first two.
SPHINXOPTS    ?=
SPHINXBUILD   ?= sphinx-build
SOURCEDIR     = sourcedocs
BUILDDIR      = docs
DOCKER_CMD		= cd /root && cp -r /app/* . && pip install poetry && poetry install && poetry run pytest

# Put it first so that "make" without argument is like "make help".
help:
	@$(SPHINXBUILD) -M help "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)


test38:
	echo "TEST PYTHON 3.8"
	docker run -i --rm -v $(shell pwd):/app python:3.8 bash -l -c "$(DOCKER_CMD)"

test39:
	echo "TEST PYTHON 3.9"
	docker run -i --rm -v $(shell pwd):/app python:3.9 bash -l -c "$(DOCKER_CMD)"

test310:
	echo "TEST PYTHON 3.10"
	docker run -i --rm -v $(shell pwd):/app python:3.10 bash -l -c "$(DOCKER_CMD)"

test311:
	echo "TEST PYTHON 3.11"
	docker run -i --rm -v $(shell pwd):/app python:3.11 bash -l -c "$(DOCKER_CMD)"

test312:
	echo "TEST PYTHON 3.12"
	docker run -i --rm -v $(shell pwd):/app python:3.12 bash -l -c "$(DOCKER_CMD)"

test: test38 test39 test310 test311 test312
	echo "OK"

clear:
	-rm -r $(shell find . -name __pycache__) build dist .mypy_cache onecache.egg-info .eggs

build: clear
	poetry build

upload_pypi: build
	pip install twine
	twine upload dist/*

.PHONY: help Makefile

# Catch-all target: route all unknown targets to Sphinx using the new
# "make mode" option.  $(O) is meant as a shortcut for $(SPHINXOPTS).
%: Makefile
	@$(SPHINXBUILD) -M $@ "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)
