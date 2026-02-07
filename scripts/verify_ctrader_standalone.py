"""
Script de Verificação Simples - cTrader Open API
================================================
Este script é INDEPENDENTE do projeto Oracle Trader.
Serve apenas para validar se as credenciais no .env estão corretas
e se é possível estabelecer conexão TCP com a API da cTrader.

Dependências:
    pip install python-dotenv twisted pyopenssl service_identity

Uso:
    python verify_ctrader_standalone.py
"""

import os
import sys
import ssl
import json
import socket
from pathlib import Path
from dotenv import load_dotenv

# Configurações cTrader (Host/Porta)
CTRADER_HOST_LIVE = "live.ctraderapi.com"
CTRADER_PORT_LIVE = 5035
CTRADER_HOST_DEMO = "demo.ctraderapi.com"
CTRADER_PORT_DEMO = 5035

def verify_credentials():
    """Carrega e valida credenciais do .env"""
    print("📂 Carregando .env...")
    
    # Tenta achar .env no diretório atual ou pai
    current_dir = Path.cwd()
    env_path = current_dir / ".env"
    
    if not env_path.exists():
        print(f"❌ .env não encontrado em: {env_path}")
        return None
        
    load_dotenv(env_path)
    
    creds = {
        "client_id": os.getenv("CTRADER_CLIENT_ID"),
        "client_secret": os.getenv("CTRADER_CLIENT_SECRET"),
        "account_id": os.getenv("CTRADER_ACCOUNT_ID"),
        "token": os.getenv("CTRADER_ACCESS_TOKEN")
    }
    
    missing = [k for k, v in creds.items() if not v]
    
    if missing:
        print(f"❌ Credenciais faltando: {', '.join(missing)}")
        return None
        
    print("✅ Credenciais carregadas!")
    print(f"   Account ID: {creds['account_id']}")
    print(f"   Client ID:  {creds['client_id'][:5]}...")
    return creds

def test_tcp_connection(host, port):
    """Teste básico de conexão TCP/SSL"""
    print(f"\n🔌 Testando conexão TCP com {host}:{port}...")
    
    try:
        # Cria socket TCP simples
        sock = socket.create_connection((host, port), timeout=5)
        
        # Envolve com SSL
        context = ssl.create_default_context()
        ssock = context.wrap_socket(sock, server_hostname=host)
        
        print(f"✅ Conexão TCP/SSL estabelecida!")
        print(f"   Cipher: {ssock.cipher()}")
        print(f"   Version: {ssock.version()}")
        
        ssock.close()
        return True
        
    except socket.timeout:
        print("❌ Timeout na conexão (Firewall?)")
    except ssl.SSLError as e:
        print(f"❌ Erro SSL: {e}")
    except Exception as e:
        print(f"❌ Erro de conexão: {e}")
        
    return False

def main():
    print("=== Teste de Conectividade cTrader ===\n")
    
    creds = verify_credentials()
    if not creds:
        return
    
    # Testa Demo e Live
    print("\n--- Testando Ambiente DEMO ---")
    demo_ok = test_tcp_connection(CTRADER_HOST_DEMO, CTRADER_PORT_DEMO)
    
    print("\n--- Testando Ambiente LIVE ---")
    live_ok = test_tcp_connection(CTRADER_HOST_LIVE, CTRADER_PORT_LIVE)
    
    print("\n" + "="*40)
    print("RELATÓRIO FINAL:")
    print(f"Credenciais: {'OK' if creds else 'FALHA'}")
    print(f"Rede Demo:   {'OK' if demo_ok else 'FALHA'}")
    print(f"Rede Live:   {'OK' if live_ok else 'FALHA'}")
    print("="*40)
    
    if demo_ok or live_ok:
        print("\nPróximos passos:")
        print("A conectividade básica está funcionando. Para testar o login real (Protobuf),")
        print("você precisará da implementação completa do `connector` da Fase 3.")

if __name__ == "__main__":
    main()
