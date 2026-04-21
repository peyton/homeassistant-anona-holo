set shell := ["bash", "-euo", "pipefail", "-c"]

bootstrap:
    uv venv --allow-existing .venv
    uv pip install --python .venv/bin/python -r requirements.txt
    hk install --mise

lint:
    if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then \
        hk run check $(find custom_components tests scripts .github/workflows -type f -print); \
    else \
        ruff format --quiet custom_components tests scripts --check; \
        ruff check custom_components tests scripts; \
        actionlint .github/workflows/*.yml; \
        ghalint run; \
    fi

fix:
    if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then \
        hk run fix $(find custom_components tests scripts .github/workflows -type f -print); \
    else \
        ruff format --quiet custom_components tests scripts; \
        ruff check --fix custom_components tests scripts; \
        actionlint .github/workflows/*.yml; \
        ghalint run; \
    fi

typecheck:
    PYRIGHT_PACKAGE="${PYRIGHT_PACKAGE:-pyright==1.1.408}"; \
    XDG_CACHE_HOME="${XDG_CACHE_HOME:-/tmp/xdg-cache}"; \
    UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/uv-cache}"; \
    UV_TOOL_DIR="${UV_TOOL_DIR:-/tmp/uv-tools}"; \
    XDG_CACHE_HOME="${XDG_CACHE_HOME}" UV_CACHE_DIR="${UV_CACHE_DIR}" UV_TOOL_DIR="${UV_TOOL_DIR}" uvx --from "${PYRIGHT_PACKAGE}" pyright --pythonpath ./.venv/bin/python custom_components/anona_holo tests scripts

test:
    .venv/bin/python -m pytest -q

check:
    just lint
    just typecheck
    just test

release-check version:
    python -m scripts.release_workflow validate-version --version "{{version}}"
    if [[ "$(git rev-parse --abbrev-ref HEAD)" != "master" ]]; then \
        echo "Releases must be cut from the master branch." >&2; \
        exit 1; \
    fi
    if [[ -n "$(git status --porcelain)" ]]; then \
        echo "Working tree must be clean before cutting a release." >&2; \
        exit 1; \
    fi
    git fetch origin master --tags
    if [[ "$(git rev-parse HEAD)" != "$(git rev-parse origin/master)" ]]; then \
        echo "Local master must match origin/master before cutting a release." >&2; \
        exit 1; \
    fi
    if git rev-parse -q --verify "refs/tags/v{{version}}" >/dev/null; then \
        echo "Tag v{{version}} already exists locally." >&2; \
        exit 1; \
    fi
    if git ls-remote --exit-code --tags origin "refs/tags/v{{version}}" >/dev/null 2>&1; then \
        echo "Tag v{{version}} already exists on origin." >&2; \
        exit 1; \
    fi

release-tag version:
    just release-check "{{version}}"
    just check
    python -m scripts.release_workflow set-manifest-version --version "{{version}}"
    git add custom_components/anona_holo/manifest.json
    git commit -m "chore(release): v{{version}}"
    git tag -a "v{{version}}" -m "v{{version}}"
    git push origin master "v{{version}}"

develop:
    if [[ ! -x "${PWD}/.venv/bin/hass" ]]; then \
        echo "Missing virtual environment. Run 'mise bootstrap' first." >&2; \
        exit 1; \
    fi
    .venv/bin/python -m scripts.ensure_dev_config --config-dir "${PWD}/config"
    export PYTHONPATH="${PYTHONPATH:-}:${PWD}/custom_components"
    exec .venv/bin/hass --config "${PWD}/config" --debug

codex-setup:
    ./scripts/codex setup

codex-develop:
    ./scripts/codex develop

codex-check:
    ./scripts/codex check

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
