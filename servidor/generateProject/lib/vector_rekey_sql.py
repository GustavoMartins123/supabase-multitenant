"""Canonical transactional SQL for physical pgvector tenant identity changes."""
from __future__ import annotations

import csv
import hashlib
import sys
from typing import TextIO
import uuid


def render(source: str, destination: str, rows: TextIO) -> str:
    for tenant in (source, destination):
        if str(uuid.UUID(tenant)) != tenant:
            raise ValueError('canonical tenant UUID required')
    if source == destination:
        raise ValueError('distinct source and destination required')
    statements = ['BEGIN;']
    for row in csv.reader(rows, strict=True):
        if len(row) != 2 or not all(row):
            raise ValueError('vector index requires bucket and name')
        bucket, index = row

        def physical(tenant: str) -> str:
            value = f'pgvector__{bucket}'.encode() + b'\0' + f'{tenant}-{index}'.encode()
            return 'vector_' + hashlib.sha256(value).hexdigest()[:24]

        old, new = physical(source), physical(destination)
        statements.append(f"""
DO $rekey$
BEGIN
  IF to_regclass('storage_vectors.{old}') IS NOT NULL
     AND to_regclass('storage_vectors.{new}') IS NULL THEN
    ALTER TABLE storage_vectors.{old} RENAME TO {new};
    IF to_regclass('storage_vectors.{old}_hnsw') IS NOT NULL THEN
      ALTER INDEX storage_vectors.{old}_hnsw RENAME TO {new}_hnsw;
    END IF;
  ELSIF to_regclass('storage_vectors.{old}') IS NULL
        AND to_regclass('storage_vectors.{new}') IS NOT NULL THEN
    NULL;
  ELSE
    RAISE EXCEPTION 'ambiguous vector table rekey: {old} -> {new}';
  END IF;
END
$rekey$;
""")
    statements.append('COMMIT;')
    return '\n'.join(statements) + '\n'


if __name__ == '__main__':
    if len(sys.argv) != 3:
        raise SystemExit('source and destination UUIDs required')
    sys.stdout.write(render(sys.argv[1], sys.argv[2], sys.stdin))
