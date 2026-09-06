#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
JAR="${1:-${OPENAPI_GENERATOR_JAR:-}}"
if [[ "${1:-}" == "--jar" ]]; then
  JAR="${2:?informe o caminho do jar}"
fi
if [[ -z "$JAR" ]]; then
  echo "defina OPENAPI_GENERATOR_JAR ou passe --jar <caminho>" >&2
  echo "download: https://repo1.maven.org/maven2/org/openapitools/openapi-generator-cli/7.12.0/openapi-generator-cli-7.12.0.jar" >&2
  exit 2
fi

python3 tools/export_openapi.py
java -jar "$JAR" generate -g dart -i docs/api/openapi.json -o studio/projects_api_client \
  --additional-properties=pubName=projects_api_client,pubVersion=0.13.0-alpha,pubDescription="Generated client for the supabase-multitenant Projects API. DO NOT EDIT BY HAND.",hideGenerationTimestamp=true,dateLibrary=core
rm -f studio/projects_api_client/git_push.sh studio/projects_api_client/.travis.yml
python3 tools/patch_dart_client.py
dart pub get --directory=studio/projects_api_client
dart analyze studio/projects_api_client/lib
