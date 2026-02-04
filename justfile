# https://just.systems/man/en/
# REQUIRES

gcloud := require("gcloud")
git := require("git")
jq := require("jq")
uv := require("uv")

# SETTINGS

set dotenv-load := true

# ENVIRONS

export UV_ENV_FILE := ".env"

# VARIABLES

SOURCES := "*.py"

# DEFAULTS

# display help information
default:
    @just --list

# TASKS

# run the app
app:
    uv run uvicorn main:app --reload --port 8080 \
    |  jq --raw-input --raw-output --color-output 'fromjson? // .'

# auth to GCP
auth:
    gcloud auth login --update-adc

# check quality
check:
    uv run ty check {{ SOURCES }}
    uv run ruff check {{ SOURCES }}
    uv run ruff format --check {{ SOURCES }}

# clean artifacts
clean:
    rm -rf .ruff_cache/
    find . -type f -name '*.py[co]' -delete
    find . -type d -name __pycache__ -exec rm -r {} \+

# clear environment
[confirm]
clear: clean
    rm -f uv.lock
    rm -rf .venv/

# deploy to cloud run
deploy: format check
    gcloud run deploy $GOOGLE_CLOUD_PROJECT \
        --region=$GOOGLE_CLOUD_RUN_LOCATION \
        --project=$GOOGLE_CLOUD_PROJECT \
        --base-image=python313 \
        --min-instances=0 \
        --max-instances=1 \
        --concurrency=100 \
        --memory=512Mi \
        --cpu=1 \
        --timeout=30 \
        --session-affinity \
        --ingress=all \
        --no-allow-unauthenticated \
        --env-vars-file=.env.prod.yaml \
        --source .

# format code and import
format:
    uv run ruff check --select=I --fix {{ SOURCES }}
    uv run ruff format {{ SOURCES }}

# install dependencies
install:
    uv sync --all-groups
    uv run pre-commit install

# run pre-commit hooks
pre-commit:
    uv run pre-commit run --all-files
