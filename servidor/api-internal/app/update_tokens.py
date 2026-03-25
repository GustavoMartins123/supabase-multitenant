import os
import asyncio
import asyncpg
from cryptography.fernet import Fernet

PROJECT_NAME = "meu_projeto"

ENV_PATH = f"/docker/projects/{PROJECT_NAME}/.env"

async def main():
    DB_DSN = os.getenv("DB_DSN")
    FERNET_SECRET = os.getenv("FERNET_SECRET")

    if not DB_DSN or not FERNET_SECRET:
        print("❌ Erro: DB_DSN ou FERNET_SECRET não encontrados no ambiente do container.")
        return

    config_token = None
    try:
        with open(ENV_PATH, "r") as f:
            for line in f:
                if line.startswith("CONFIG_TOKEN_PROJETO="):
                    config_token = line.split("=", 1)[1].strip()
                    break
    except FileNotFoundError:
        print(f"❌ Arquivo não encontrado em: {ENV_PATH}")
        return

    if not config_token:
        print(f"❌ CONFIG_TOKEN_PROJETO não encontrado dentro de {ENV_PATH}")
        return

    print(f"🔍 Token encontrado: {config_token[:6]}... (ocultado)")

    fernet = Fernet(FERNET_SECRET.encode())
    encrypted_token = fernet.encrypt(config_token.encode()).decode()

    pool = await asyncpg.create_pool(DB_DSN)
    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE projects SET config_token = $1 WHERE name = $2",
            encrypted_token, PROJECT_NAME
        )
        print(f"✅ Sucesso! {result} - Token criptografado e salvo no banco principal.")
    
    await pool.close()

if __name__ == "__main__":
    asyncio.run(main())
