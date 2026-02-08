import sys
import os
import threading
import time
from twisted.internet import reactor
from ctrader_open_api import Client, TcpProtocol, EndPoints, Protobuf
from ctrader_open_api.messages.OpenApiMessages_pb2 import *
from ctrader_open_api.messages.OpenApiModelMessages_pb2 import *
from dotenv import load_dotenv

# Carrega variáveis de ambiente
load_dotenv()

CTRADER_CLIENT_ID = os.getenv("CTRADER_CLIENT_ID")
CTRADER_CLIENT_SECRET = os.getenv("CTRADER_CLIENT_SECRET")
CTRADER_ACCESS_TOKEN = os.getenv("CTRADER_ACCESS_TOKEN")
HOST = EndPoints.PROTOBUF_DEMO_HOST
PORT = EndPoints.PROTOBUF_PORT

if not CTRADER_CLIENT_ID or not CTRADER_ACCESS_TOKEN:
    print("❌ Erro: CTRADER_CLIENT_ID ou CTRADER_ACCESS_TOKEN não encontrados no .env")
    sys.exit(1)

print(f"🔄 Conectando a {HOST}:{PORT} (Threaded Reactor)...")

class AccountLister:
    def __init__(self):
        self.client = Client(HOST, PORT, TcpProtocol)
        self.client.setConnectedCallback(self.connected)
        self.client.setDisconnectedCallback(self.disconnected)
        self.client.setMessageReceivedCallback(self.message_received)
        self._done = threading.Event()
        self._error = None

    def start(self):
        # Inicia reactor em thread separada para evitar bloqueio e problemas de sinal
        self._reactor_thread = threading.Thread(target=reactor.run, kwargs={'installSignalHandlers': False}, daemon=True)
        self._reactor_thread.start()
        
        # Agenda o startService no loop do reactor
        reactor.callFromThread(self.client.startService)
        
        # Aguarda conclusão
        self._done.wait(timeout=30)
        
        if self._error:
            print(f"❌ Erro: {self._error}")
        
        self.stop()

    def stop(self):
        if self.client:
            reactor.callFromThread(self.client.stopService)
        # Não paramos o reactor aqui para não quebrar a thread daemon abruptamente, 
        # mas em um script one-shot o programa vai sair de qualquer jeito.

    def connected(self, client):
        print("✅ Conectado TCP. Autenticando App...")
        req = ProtoOAApplicationAuthReq()
        req.clientId = CTRADER_CLIENT_ID
        req.clientSecret = CTRADER_CLIENT_SECRET
        client.send(req)

    def disconnected(self, client, reason):
        if not self._done.is_set():
            self._error = f"Desconectado: {reason}"
            self._done.set()

    def message_received(self, client, message):
        try:
            if message.payloadType == ProtoOAApplicationAuthRes().payloadType:
                print("✅ App Auth OK. Solicitando contas...")
                req = ProtoOAGetAccountListByAccessTokenReq()
                req.accessToken = CTRADER_ACCESS_TOKEN
                client.send(req)

            elif message.payloadType == ProtoOAGetAccountListByAccessTokenRes().payloadType:
                res = Protobuf.extract(message)
                print(f"\n📋 Contas vinculadas ao Token ({len(res.ctidTraderAccount)} encontradas):")
                print("=" * 80)
                print(f"{'ID (ctidTraderAccountId)':<25} {'Live/Demo':<10} {'Trader Login':<15} {'Last Access'}")
                print("-" * 80)
                
                for acct in res.ctidTraderAccount:
                    live_demo = "Live" if acct.isLive else "Demo"
                    last_access = str(acct.lastConnectingTimestamp) if hasattr(acct, 'lastConnectingTimestamp') else "N/A"
                    login = str(acct.traderLogin) if hasattr(acct, 'traderLogin') else "N/A"
                    print(f"{acct.ctidTraderAccountId:<25} {live_demo:<10} {login:<15} {last_access}")
                
                print("=" * 80)
                print("=" * 80)
                
                print("\n🛠️  SUGESTÃO DE CONFIGURAÇÃO (.env) 🛠️")
                print("Copie e cole o bloco abaixo no seu arquivo .env para a conta desejada:\n")

                for acct in res.ctidTraderAccount:
                    live_demo = "live" if acct.isLive else "demo"
                    login = str(acct.traderLogin) if hasattr(acct, 'traderLogin') else "N/A"
                    aid = acct.ctidTraderAccountId
                    
                    print(f"--- OPÇÃO: Conta {login} ({live_demo.upper()}) ---")
                    print(f"# ⚠️  ID DA CONTA (Não confundir com Login {login})")
                    print(f"CTRADER_ACCOUNT_ID={aid}")
                    print(f"# Ambiente de conexão")
                    print(f"CTRADER_ENVIRONMENT={live_demo}")
                    print("-" * 40)

                print("\n💡 DICA: O 'CTRADER_ACCOUNT_ID' é o identificador interno único, diferente do número de login visível no cTrader.")
                self._done.set()

            elif message.payloadType == ProtoOAErrorRes().payloadType:
                err = Protobuf.extract(message)
                self._error = f"API Error: {err.errorCode} - {err.description}"
                self._done.set()
                
        except Exception as e:
            self._error = str(e)
            self._done.set()

def main():
    lister = AccountLister()
    lister.start()

if __name__ == "__main__":
    main()
