.PHONY: install run test lint format upgrade publish clean
.DEFAULT_GOAL := run

ifeq ($(OS),Windows_NT)
    BASH := $(shell powershell -NoProfile -ExecutionPolicy Bypass -File tools/find-bash.ps1)
    ifeq ($(BASH),)
        $(error Could not locate Git bash - run tools/install-bash.ps1 (open a new terminal if you just installed it))
    endif
    SHELL := $(BASH)
else
    SHELL := bash
endif
.SHELLFLAGS := -euo pipefail -c

UV := ./tools/uv.sh
UV_RUN := $(UV) run --locked

INSTALL_STAMP := build/.install-stamp

$(INSTALL_STAMP): tools/install.sh tools/install-bash.ps1
	@./tools/install.sh
	@mkdir -p $(@D) && touch $@

install: $(INSTALL_STAMP)

run: install
	@$(UV_RUN) fac -C examples/hello

lint: install
	@$(UV_RUN) ruff check
	@$(UV_RUN) ruff format --check
	@$(UV_RUN) ty check

test: install lint
	@$(UV_RUN) pytest

format: install
	@$(UV_RUN) ruff check --fix
	@$(UV_RUN) ruff format

upgrade: install
	@./tools/install.sh --update
	@$(UV) lock --upgrade

publish: install
	@$(UV) build --out-dir build/dist
	@$(UV) publish build/dist/*

clean:
	@rm -rf build
