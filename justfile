set shell := ["bash", "-euo", "pipefail", "-c"]

bootstrap:
    uv venv --allow-existing .venv
    uv pip install --python .venv/bin/python -r requirements.txt
    hk install --mise

lint:
    if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then \
        hk run check $(find custom_components tests .github/workflows -type f -print); \
    else \
        ruff format --quiet custom_components tests --check; \
        ruff check custom_components tests; \
        actionlint .github/workflows/*.yml; \
        ghalint run; \
    fi

fix:
    if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then \
        hk run fix $(find custom_components tests .github/workflows -type f -print); \
    else \
        ruff format --quiet custom_components tests; \
        ruff check --fix custom_components tests; \
        actionlint .github/workflows/*.yml; \
        ghalint run; \
    fi

typecheck:
    PYRIGHT_PACKAGE="${PYRIGHT_PACKAGE:-pyright==1.1.408}"; \
    XDG_CACHE_HOME="${XDG_CACHE_HOME:-/tmp/xdg-cache}"; \
    UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/uv-cache}"; \
    UV_TOOL_DIR="${UV_TOOL_DIR:-/tmp/uv-tools}"; \
    XDG_CACHE_HOME="${XDG_CACHE_HOME}" UV_CACHE_DIR="${UV_CACHE_DIR}" UV_TOOL_DIR="${UV_TOOL_DIR}" uvx --from "${PYRIGHT_PACKAGE}" pyright --pythonpath ./.venv/bin/python custom_components/anona_security tests

test:
    .venv/bin/python -m pytest -q

check:
    just lint
    just typecheck
    just test

develop:
    if [[ ! -x "${PWD}/.venv/bin/hass" ]]; then \
        echo "Missing virtual environment. Run 'mise bootstrap' first." >&2; \
        exit 1; \
    fi
    if [[ ! -d "${PWD}/config" ]]; then \
        mkdir -p "${PWD}/config"; \
        .venv/bin/hass --config "${PWD}/config" --script ensure_config; \
    fi
    export PYTHONPATH="${PYTHONPATH:-}:${PWD}/custom_components"
    exec .venv/bin/hass --config "${PWD}/config" --debug

act args='':
    act --bind --container-architecture linux/amd64 -P ubuntu-latest=ghcr.io/catthehacker/ubuntu:act-latest {{ args }}

act-lint:
    act --bind --container-architecture linux/amd64 -P ubuntu-latest=ghcr.io/catthehacker/ubuntu:act-latest pull_request -W .github/workflows/lint.yml

act-validate:
    if [[ -z "${GITHUB_TOKEN:-}" ]]; then \
        echo "GITHUB_TOKEN is required for just act-validate because hacs/action calls the GitHub API." >&2; \
        exit 1; \
    fi
    act --bind --container-architecture linux/amd64 -P ubuntu-latest=ghcr.io/catthehacker/ubuntu:act-latest pull_request -W .github/workflows/validate.yml -e .github/act/pull_request.json -j hacs
    if [[ "${SKIP_LOCAL_HASSFEST:-0}" == "1" || ( "$(uname -s)" == "Darwin" && "$(uname -m)" == "arm64" ) ]]; then \
        echo "Skipping local Hassfest execution because ghcr.io/home-assistant/hassfest currently crashes during dependency validation on this platform. GitHub Actions remains the authoritative Hassfest environment."; \
    else \
        docker run --rm -v "${PWD}:/github/workspace" ghcr.io/home-assistant/hassfest; \
    fi

act-release:
    act --bind --container-architecture linux/amd64 -P ubuntu-latest=ghcr.io/catthehacker/ubuntu:act-latest push -W .github/workflows/release.yml -e .github/act/release.json
