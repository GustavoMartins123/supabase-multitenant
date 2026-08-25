"""O .env do servidor e lido pelo bash E pelo host-agent.

Caminhos com espaco (`HOST_PROJECT_ROOT="/home/x/Area de trabalho/..."`)
precisam de aspas para o `source` do bash. O leitor canonico do agent
rejeitava qualquer valor citado, entao `recreate_services` quebrava com
"Entrada nao canonica no .env: HOST_PROJECT_ROOT" em toda instalacao.
"""

from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
AGENT_ROOT = ROOT / "servidor" / "host-agent"
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from hostagent.envfile import (  # noqa: E402
    read_canonical_env_value,
    upsert_env_value,
)


class CanonicalEnvQuotingContract(unittest.TestCase):
    def _read(self, line: str, key: str) -> str | None:
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / ".env"
            path.write_text(line + "\n", encoding="utf-8")
            return read_canonical_env_value(path, key)

    def test_quoted_paths_with_spaces_are_accepted(self) -> None:
        self.assertEqual(
            "/home/gustavo/Área de trabalho/supabase-git/x",
            self._read(
                'HOST_PROJECT_ROOT="/home/gustavo/Área de trabalho/supabase-git/x"',
                "HOST_PROJECT_ROOT",
            ),
        )
        self.assertEqual("literal", self._read("K='literal'", "K"))
        self.assertEqual("", self._read('K=""', "K"))

    def test_unquoted_values_keep_working(self) -> None:
        self.assertEqual("10.72.4.107", self._read("SERVER_URL=10.72.4.107", "SERVER_URL"))

    def test_values_bash_would_reinterpret_are_rejected(self) -> None:
        ambiguous = [
            ('K="tem $VAR"', "K"),          # expansao
            ('K="tem `cmd`"', "K"),         # substituicao de comando
            ('K="tem \\\\ escape"', "K"),   # escape
            ('K="aspas " no meio"', "K"),   # aspas desbalanceadas
            ('export K="x"', "K"),          # export
            ('K= "espaco apos ="', "K"),    # valor nao normalizado
        ]
        for line, key in ambiguous:
            with self.subTest(line=line):
                with self.assertRaises(RuntimeError):
                    self._read(line, key)

    def test_upsert_refuses_values_that_would_need_quotes(self) -> None:
        """upsert grava sem aspas: um valor que precise delas corromperia."""
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / ".env"
            path.write_text("K=antigo\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                upsert_env_value(path, "K", "com espaco")
            self.assertEqual("antigo", read_canonical_env_value(path, "K"))
            upsert_env_value(path, "K", "novo")
            self.assertEqual("novo", read_canonical_env_value(path, "K"))


class SettingsWriteOwnershipContract(unittest.TestCase):
    """A API grava o .env do projeto como root, por um bind mount.

    `shutil.copymode` preserva o modo mas nao o dono. Sem restaurar uid/gid,
    o arquivo (modo 600) passa a pertencer ao root e o host-agent, que roda
    como usuario de servico, perde o acesso — recreate/rename/rotate quebram
    com PermissionError logo depois de salvar qualquer configuracao.
    """

    def test_write_restores_the_original_owner(self) -> None:
        source = (
            ROOT / "servidor/api-internal/app/project_settings.py"
        ).read_text(encoding="utf-8")
        writer = source.split("def _write_env_whitelisted(", 1)[1]
        writer = writer.split("\ndef ", 1)[0]
        self.assertIn("os.stat(env_path)", writer)
        self.assertIn("os.chown(temp_path", writer)
        # O chown precisa acontecer antes da troca atomica.
        self.assertLess(
            writer.index("os.chown(temp_path"),
            writer.index("os.replace(temp_path, env_path)"),
        )


if __name__ == "__main__":
    unittest.main()
