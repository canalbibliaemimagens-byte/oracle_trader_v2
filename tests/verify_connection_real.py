"""
Oracle Trader v2.0 — Verificação de Conexão Real com cTrader
==============================================================

Script manual para verificar credenciais .env e futura conexão real.
"""

import asyncio
import os
import logging
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

from oracle_trader_v2.core.models import AccountInfo
from oracle_trader_v2.connector.mock.client import MockConnector

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("VerifyConnection")

ROOT = Path(__file__).parent.parent


async def main():
    print("🔌 Verificando Conexão com cTrader (Real/Demo)...")

    env_path = ROOT / ".env"
    if not env_path.exists():
        print("❌ Arquivo .env não encontrado!")
        print(f"   Por favor, copie .env.example para {env_path}")
        return

    if load_dotenv:
        load_dotenv(env_path)

    client_id = os.getenv("CTRADER_CLIENT_ID")
    client_secret = os.getenv("CTRADER_CLIENT_SECRET")
    token = os.getenv("CTRADER_ACCESS_TOKEN")
    account_id = os.getenv("CTRADER_ACCOUNT_ID")

    print(f"   Client ID: {'OK' if client_id else 'MISSING'}")
    print(f"   Secret:    {'OK' if client_secret else 'MISSING'}")
    print(f"   Token:     {'OK' if token else 'MISSING'}")
    print(f"   Account:   {'OK' if account_id else 'MISSING'}")

    if not all([client_id, client_secret, token, account_id]):
        print("\n❌ Faltam credenciais no arquivo .env.")
        return

    print("\n✅ Credenciais detectadas.")
    print("⚠️  Para testar conexão real, finalize a implementação do CtraderConnector.")


if __name__ == "__main__":
    asyncio.run(main())
