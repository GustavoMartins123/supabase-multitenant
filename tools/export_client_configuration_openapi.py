"""Export the public discovery contract separately from the administrative API."""

import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / 'docs/api/client-configuration.openapi.json'


def main():
    spec = importlib.util.spec_from_file_location('client_configuration_service', ROOT/'servidor/client-configuration/app.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rendered = json.dumps(module.app.openapi(), indent=2, sort_keys=True) + '\n'
    if '--check' in sys.argv:
        if TARGET.read_text(encoding='utf-8') != rendered:
            print('Public discovery OpenAPI is out of sync')
            return 1
        print('Public discovery OpenAPI is in sync')
    else:
        TARGET.write_text(rendered, encoding='utf-8', newline='\n')
        print('Public discovery OpenAPI exported')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
