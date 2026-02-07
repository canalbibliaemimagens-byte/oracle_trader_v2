import os
import requests
import json
from dotenv import load_dotenv

def main():
    print("🔍 Ctrader API - List Accounts")
    print("===============================")
    
    # 1. Load .env
    load_dotenv()
    token = os.getenv("CTRADER_ACCESS_TOKEN")
    
    if not token:
        print("❌ Erro: CTRADER_ACCESS_TOKEN não encontrado no .env")
        print("   Execute 'python scripts/get_token.py' para gerar um.")
        return

    # 2. API Endpoint
    # Docs: https://openapi.ctrader.com/docs/api-reference/accounts/get-accounts-list
    url = "https://openapi.ctrader.com/connect/tradingaccounts"
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    print(f"🔄 Consultando API: {url}")
    print(f"🔑 Token parcial: {token[:10]}...")

    try:
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            print("\n✅ SUCESSO! Resposta recebida:")
            # print(json.dumps(data, indent=2)) # Raw JSON if needed
            
            accounts = data.get('data', [])
            if not accounts:
                print("   Nenhuma conta vinculada a este token.")
            else:
                print(f"   Encontradas {len(accounts)} contas vinculadas:")
                print("-" * 50)
                print(f"{'Account ID':<15} | {'Login':<10} | {'Live':<6} | {'Currency':<5}")
                print("-" * 50)
                
                for acc in accounts:
                    aid = str(acc.get('accountId', 'N/A'))
                    login = str(acc.get('traderLogin', 'N/A'))
                    is_live = "YES" if acc.get('live') else "NO"
                    currency = acc.get('currency', 'USD')
                    print(f"{aid:<15} | {login:<10} | {is_live:<6} | {currency:<5}")
                print("-" * 50)
                
                # Update .env hint
                first_id = accounts[0].get('accountId')
                print(f"\n💡 Dica: Atualize o CTRADER_ACCOUNT_ID no seu .env para: {first_id}")

        elif response.status_code == 401:
            print("\n❌ Erro 401: Não autorizado.")
            print("   O token pode estar expirado ou ser inválido.")
            print("   Tente gerar um novo token.")
            
        elif response.status_code == 403:
            print("\n❌ Erro 403: Proibido.")
            print("   Verifique as permissões (Escopo) do seu token.")
            
        else:
            print(f"\n❌ Erro {response.status_code}:")
            print(response.text)

    except requests.exceptions.ConnectionError:
        print("\n❌ Erro de conexão.")
        print("   Verifique sua internet ou se há bloqueios (hosts/firewall).")
    except Exception as e:
        print(f"\n❌ Erro inesperado: {e}")

if __name__ == "__main__":
    main()
