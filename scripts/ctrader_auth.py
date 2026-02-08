import os
import urllib.parse
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests
import json
import threading
import time
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.getenv("CTRADER_CLIENT_ID")
CLIENT_SECRET = os.getenv("CTRADER_CLIENT_SECRET")
REDIRECT_URI = "http://localhost:5000/callback"
SCOPE = "trading"

AUTH_CODE = None
SERVER_RUNNING = True

class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global AUTH_CODE
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        if 'code' in params:
            AUTH_CODE = params['code'][0]
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write("""
                <html>
                <head><title>Autenticação cTrader</title></head>
                <body style="font-family: Arial; text-align: center; padding: 50px;">
                    <h1 style="color: green;">✅ Autenticado com sucesso!</h1>
                    <p>Você pode fechar esta janela e voltar ao terminal.</p>
                </body>
                </html>
            """.encode())
        else:
            self.send_response(400)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(b"<h1>Erro: Codigo nao encontrado.</h1>")
    
    def log_message(self, format, *args):
        return

def start_server():
    server = HTTPServer(('localhost', 5000), CallbackHandler)
    while SERVER_RUNNING and AUTH_CODE is None:
        server.handle_request()

def check_connectivity():
    """Verifica se consegue acessar o cTrader Connect"""
    print("\n🔍 Verificando conectividade com cTrader...")
    try:
        response = requests.get("https://connect.ctrader.com", timeout=10)
        print("✅ Conexão com cTrader OK!")
        return True
    except requests.exceptions.ConnectionError:
        print("❌ Erro de conexão com connect.ctrader.com")
        return False
    except requests.exceptions.Timeout:
        print("❌ Timeout ao tentar conectar")
        return False
    except Exception as e:
        print(f"❌ Erro inesperado: {e}")
        return False

def show_troubleshooting():
    """Mostra dicas de troubleshooting"""
    print("\n" + "="*60)
    print("🔧 POSSÍVEIS SOLUÇÕES:")
    print("="*60)
    print("1. Verifique sua conexão com a internet")
    print("2. Verifique se há firewall bloqueando o acesso")
    print("3. Tente desabilitar VPN temporariamente")
    print("4. Verifique se o site funciona no navegador:")
    print("   https://connect.ctrader.com")
    print("5. Tente usar outro navegador ou modo anônimo")
    print("6. Verifique se suas credenciais CLIENT_ID e CLIENT_SECRET")
    print("   estão corretas no arquivo .env")
    print("="*60)

def get_token():
    # Verificar credenciais
    if not CLIENT_ID or not CLIENT_SECRET:
        print("\n❌ ERRO: CLIENT_ID ou CLIENT_SECRET não encontrados no .env")
        print("\nCrie um arquivo .env com:")
        print("CTRADER_CLIENT_ID=seu_client_id")
        print("CTRADER_CLIENT_SECRET=seu_client_secret")
        print("CTRADER_ACCESS_TOKEN=")
        return
    
    print(f"\n✅ Credenciais carregadas:")
    print(f"   CLIENT_ID: {CLIENT_ID[:10]}...")
    print(f"   CLIENT_SECRET: {CLIENT_SECRET[:10]}...")
    
    # Verificar conectividade
    if not check_connectivity():
        show_troubleshooting()
        
        print("\n❓ Deseja tentar mesmo assim? (s/n): ", end="")
        if input().lower() != 's':
            return
    
    # Start Server in Thread
    print("\n🚀 Iniciando servidor local na porta 5000...")
    t = threading.Thread(target=start_server, daemon=True)
    t.start()
    time.sleep(1)  # Give server time to start

    # Build Auth URL (usando connect.spotware.com)
    auth_url = (
        f"https://connect.spotware.com/apps/auth?"
        f"client_id={CLIENT_ID}&"
        f"response_type=code&"
        f"redirect_uri={urllib.parse.quote(REDIRECT_URI)}&"
        f"scope={SCOPE}"
    )
    
    print("\n" + "="*60)
    print("📋 INSTRUÇÕES PASSO A PASSO")
    print("="*60)
    print("1. Abra este link no navegador:")
    print(f"\n   {auth_url}\n")
    print("2. Faça login na sua conta cTrader")
    print("3. Autorize a aplicação")
    print("4. Você será redirecionado automaticamente")
    print("="*60)
    print("\n⚠️  IMPORTANTE: Se o navegador mostrar erro de conexão:")
    print("   - Copie a URL completa da barra de endereços")
    print("   - Cole aqui quando solicitado")
    print("   - A URL terá um parâmetro 'code=...'")
    print("="*60)
    
    # Try opening browser
    print("\n🌐 Tentando abrir o navegador automaticamente...")
    try:
        webbrowser.open(auth_url)
        print("✅ Navegador aberto! Aguarde o redirecionamento...")
    except Exception as e:
        print(f"⚠️  Não foi possível abrir o navegador: {e}")
        print("   Copie e cole a URL manualmente no navegador.")

    # Wait for code
    global AUTH_CODE, SERVER_RUNNING
    
    print("\n⏳ Aguardando autenticação...")
    print("   (Pressione Enter se precisar colar o código manualmente)")
    
    # Wait up to 60 seconds for automatic callback
    for i in range(60):
        if AUTH_CODE:
            break
        time.sleep(1)
        if i % 10 == 0 and i > 0:
            print(f"   ... ainda aguardando ({i}s)")
    
    if not AUTH_CODE:
        print("\n⌛ Timeout - não recebeu callback automático")
        print("\n📋 Cole a URL completa para qual você foi redirecionado")
        print("   (ou apenas o código após 'code='): ")
        manual_input = input("> ").strip()
        
        if manual_input:
            # Try to extract code from URL or use as-is
            if 'code=' in manual_input:
                try:
                    parsed = urllib.parse.urlparse(manual_input)
                    params = urllib.parse.parse_qs(parsed.query)
                    AUTH_CODE = params['code'][0]
                except:
                    print("❌ Não foi possível extrair o código da URL")
            else:
                AUTH_CODE = manual_input
    
    SERVER_RUNNING = False
    
    if not AUTH_CODE:
        print("\n❌ Não foi possível obter o código de autorização.")
        return

    print(f"\n✅ Código obtido: {AUTH_CODE[:15]}...")

    # Exchange code for token (usando openapi.ctrader.com)
    print("\n🔄 Trocando código por token de acesso...")
    token_url = "https://openapi.ctrader.com/apps/token"
    
    payload = {
        'grant_type': 'authorization_code',
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'redirect_uri': REDIRECT_URI,
        'code': AUTH_CODE
    }
    
    try:
        # Usar GET conforme documentação oficial
        response = requests.get(token_url, params=payload, timeout=30)
        
        if response.status_code != 200:
            print(f"\n❌ Erro HTTP {response.status_code}")
            print(f"Resposta: {response.text}")
            return
        
        data = response.json()
        
        if 'access_token' not in data:
            print(f"\n❌ Token não encontrado na resposta: {data}")
            return
        
        token = data['access_token']
        refresh_token = data.get('refresh_token', '')
        expires_in = data.get('expires_in', 0)
        
        print(f"\n🎉 TOKEN GERADO COM SUCESSO!")
        print(f"\n📝 Access Token: {token[:20]}...")
        print(f"⏰ Expira em: {expires_in} segundos ({expires_in/3600:.1f} horas)")
        
        # Save to .env
        env_path = '.env'
        if os.path.exists(env_path):
            with open(env_path, 'r') as f:
                lines = f.readlines()
            
            token_found = False
            with open(env_path, 'w') as f:
                for line in lines:
                    if line.startswith("CTRADER_ACCESS_TOKEN="):
                        f.write(f"CTRADER_ACCESS_TOKEN={token}\n")
                        token_found = True
                    elif line.startswith("CTRADER_REFRESH_TOKEN=") and refresh_token:
                        f.write(f"CTRADER_REFRESH_TOKEN={refresh_token}\n")
                    else:
                        f.write(line)
                
                # Add token if not found
                if not token_found:
                    f.write(f"\nCTRADER_ACCESS_TOKEN={token}\n")
                    if refresh_token:
                        f.write(f"CTRADER_REFRESH_TOKEN={refresh_token}\n")
            
            print(f"\n✅ Token salvo em {env_path}")
        else:
            print(f"\n⚠️  Arquivo .env não encontrado. Criando...")
            with open(env_path, 'w') as f:
                f.write(f"CTRADER_CLIENT_ID={CLIENT_ID}\n")
                f.write(f"CTRADER_CLIENT_SECRET={CLIENT_SECRET}\n")
                f.write(f"CTRADER_ACCESS_TOKEN={token}\n")
                if refresh_token:
                    f.write(f"CTRADER_REFRESH_TOKEN={refresh_token}\n")
            print(f"✅ Arquivo {env_path} criado com sucesso!")
        
        print("\n" + "="*60)
        print("✅ PROCESSO CONCLUÍDO COM SUCESSO!")
        print("="*60)
        
    except requests.exceptions.ConnectionError as e:
        print(f"\n❌ Erro de conexão ao trocar o token: {e}")
        show_troubleshooting()
    except requests.exceptions.Timeout:
        print(f"\n❌ Timeout ao trocar o token")
    except Exception as e:
        print(f"\n❌ Erro ao trocar o token: {e}")
        if 'response' in locals():
            print(f"Resposta do servidor: {response.text}")

if __name__ == "__main__":
    print("="*60)
    print("🔐 GERADOR DE TOKEN - cTrader API")
    print("="*60)
    get_token()