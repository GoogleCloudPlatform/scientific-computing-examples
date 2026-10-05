#!/bin/bash
BLUEPRINT_PATH=$1

if [ -z "$BLUEPRINT_PATH" ]; then
    echo "ERROR: Please provide the path to the blueprint YAML file."
    echo "Usage: ./validate_blueprint.sh <blueprint_path>"
    exit 1
fi

if ! command -v gcluster &> /dev/null; then
    echo "WARNING: 'gcluster' CLI is not installed locally. Performing basic YAML linting instead..."
    python3 -c "import yaml, sys; yaml.safe_load(open(sys.argv[1]))" "$BLUEPRINT_PATH" && echo "SUCCESS: Blueprint is syntactically valid YAML."
    exit 0
fi

echo "Running gcluster validation on $BLUEPRINT_PATH..."
gcluster validate "$BLUEPRINT_PATH"