import os
import sys
import threading
import time
import pandas as pd
from datetime import datetime
from twisted.internet import reactor
from ctrader_open_api import Client, TcpProtocol, EndPoints, Protobuf
from ctrader_open_api.messages.OpenApiMessages_pb2 import *
from ctrader_open_api.messages.OpenApiModelMessages_pb2 import *
from dotenv import load_dotenv

# Carrega .env
load_dotenv()

CTRADER_CLIENT_ID = os.getenv("CTRADER_CLIENT_ID")
CTRADER_CLIENT_SECRET = os.getenv("CTRADER_CLIENT_SECRET")
CTRADER_ACCESS_TOKEN = os.getenv("CTRADER_ACCESS_TOKEN")
CTRADER_ACCOUNT_ID = os.getenv("CTRADER_ACCOUNT_ID")

if not all([CTRADER_CLIENT_ID, CTRADER_CLIENT_SECRET, CTRADER_ACCESS_TOKEN, CTRADER_ACCOUNT_ID]):
    print("❌ Erro: Credenciais incompletas no .env")
    sys.exit(1)

CTRADER_ACCOUNT_ID = int(CTRADER_ACCOUNT_ID)
SYMBOL = "EURUSD"
TIMEFRAME = "M15"
PERIOD_NAME = "M15" # Para mapeamento
ENVIRONMENT = os.getenv("CTRADER_ENVIRONMENT", "demo").lower()
HOST = EndPoints.PROTOBUF_LIVE_HOST if ENVIRONMENT == "live" else EndPoints.PROTOBUF_DEMO_HOST
PORT = EndPoints.PROTOBUF_PORT
print(f"🌍 Ambiente: {ENVIRONMENT.upper()} ({HOST}:{PORT})")

# Mapeamento API
TIMEFRAME_TO_PERIOD = {
    "M1": 1, "M5": 5, "M15": 7, "H1": 9, "H4": 10, "D1": 12
}

print(f"🔄 Iniciando Downloader Local para {SYMBOL} {TIMEFRAME}...")

class DataDownloader:
    def __init__(self):
        self.client = Client(HOST, PORT, TcpProtocol)
        self.client.setConnectedCallback(self.connected)
        self.client.setDisconnectedCallback(self.disconnected)
        self.client.setMessageReceivedCallback(self.message_received)
        self._done = threading.Event()
        self._error = None
        
        self.symbol_id = None
        self.bars = []
        
        # Controle de download
        self.to_timestamp = int(datetime.utcnow().timestamp() * 1000)
        # Baixar últimos 30 dias para teste rápido
        self.from_timestamp = int((datetime.utcnow().timestamp() - (30 * 86400)) * 1000) 
        self.current_from = self.from_timestamp

    def start(self):
        self._reactor_thread = threading.Thread(target=reactor.run, kwargs={'installSignalHandlers': False}, daemon=True)
        self._reactor_thread.start()
        reactor.callFromThread(self.client.startService)
        
        self._done.wait(timeout=60) # Timeout geral
        
        if self._error:
            print(f"\n❌ Erro: {self._error}")
        else:
            print(f"\n✅ Download concluído! Total barras: {len(self.bars)}")
            # Salvar CSV para validar
            if self.bars:
                df = pd.DataFrame(self.bars)
                filename = f"data_{SYMBOL}_{TIMEFRAME}.csv"
                df.to_csv(filename, index=False)
                print(f"📁 Salvo em: {filename}")
        
        self.stop()

    def stop(self):
        if self.client:
            reactor.callFromThread(self.client.stopService)

    def connected(self, client):
        print("✅ Conectado TCP. Autenticando App...")
        msg = ProtoOAApplicationAuthReq()
        msg.clientId = CTRADER_CLIENT_ID
        msg.clientSecret = CTRADER_CLIENT_SECRET
        client.send(msg)

    def disconnected(self, client, reason):
        if not self._done.is_set():
            self._error = f"Desconectado: {reason}"
            self._done.set()

    def message_received(self, client, message):
        try:
            # 1. App Auth
            if message.payloadType == ProtoOAApplicationAuthRes().payloadType:
                print("✅ App Auth OK. Listando contas disponíveis...")
                msg = ProtoOAGetAccountListByAccessTokenReq()
                msg.accessToken = CTRADER_ACCESS_TOKEN
                client.send(msg)

            # 1.5 List Accounts Response
            elif message.payloadType == ProtoOAGetAccountListByAccessTokenRes().payloadType:
                res = Protobuf.extract(message)
                found = False
                with open("accounts_found.txt", "w", encoding="utf-8") as f:
                    f.write(f"📋 Contas encontradas: {len(res.ctidTraderAccount)}\n")
                    for acct in res.ctidTraderAccount:
                        live_str = "LIVE" if acct.isLive else "DEMO"
                        login = getattr(acct, 'traderLogin', 'N/A')
                        line = f"ID: {acct.ctidTraderAccountId} ({live_str}) Login: {login}\n"
                        f.write(line)
                        print(f"   - {line.strip()}")
                        if acct.ctidTraderAccountId == CTRADER_ACCOUNT_ID:
                            found = True
                
                if not found:
                    self._error = f"ID {CTRADER_ACCOUNT_ID} não está na lista. Veja accounts_found.txt"
                    self._done.set()
                    return

                print(f"✅ Conta {CTRADER_ACCOUNT_ID} confirmada. Autenticando...")
                msg = ProtoOAAccountAuthReq()
                msg.accessToken = CTRADER_ACCESS_TOKEN
                msg.ctidTraderAccountId = CTRADER_ACCOUNT_ID
                client.send(msg)

            # 2. Account Auth

            # 2. Account Auth
            elif message.payloadType == ProtoOAAccountAuthRes().payloadType:
                print("✅ Conta Autenticada. Buscando Símbolos...")
                msg = ProtoOASymbolsListReq()
                msg.ctidTraderAccountId = CTRADER_ACCOUNT_ID
                client.send(msg)

            # 3. Lista de Símbolos
            elif message.payloadType == ProtoOASymbolsListRes().payloadType:
                res = Protobuf.extract(message)
                # The original debug writing is moved to _on_symbol_details
                # if res.symbol:
                #     s = res.symbol[0] 
                #     with open("debug_symbol.txt", "w") as f:
                #         f.write(f"minVolume={getattr(s, 'minVolume', 'N/A')}\\n")
                #         f.write(f"stepVolume={getattr(s, 'stepVolume', 'N/A')}\\n")
                #         f.write(f"maxVolume={getattr(s, 'maxVolume', 'N/A')}\\n")
                #     print(f"DEBUG RAW SYMBOL: minVolume={getattr(s, 'minVolume', 'N/A')}") 
                #     pass 
                for sym in res.symbol:
                    name = sym.symbolName if hasattr(sym, 'symbolName') else str(sym.symbolId)
                    if name == SYMBOL:
                        self.symbol_id = sym.symbolId
                        print(f"✅ Símbolo {SYMBOL} encontrado (ID: {self.symbol_id})")
                        break
                
                if self.symbol_id:
                    print(f"✅ Símbolo {SYMBOL} encontrado (ID: {self.symbol_id}). Solicitando detalhes...")
                    msg = ProtoOASymbolByIdReq()
                    msg.ctidTraderAccountId = CTRADER_ACCOUNT_ID
                    msg.symbolId.append(self.symbol_id)
                    client.send(msg)
                else:
                    self._error = f"Símbolo {SYMBOL} não encontrado na conta."
                    self._done.set()

            # 3.5 Symbol Details
            elif message.payloadType == ProtoOASymbolByIdRes().payloadType:
                res = Protobuf.extract(message)
                if res.symbol:
                    s = res.symbol[0]
                    with open("debug_symbol.txt", "w") as f:
                        f.write(f"minVolume={getattr(s, 'minVolume', 'N/A')}\n")
                        f.write(f"stepVolume={getattr(s, 'stepVolume', 'N/A')}\n")
                        f.write(f"maxVolume={getattr(s, 'maxVolume', 'N/A')}\n")
                    print(f"DEBUG RAW SYMBOL: minVolume={getattr(s, 'minVolume', 'N/A')}")
            
                    # CORREÇÃO: minVolume vem em centavos? (100k = 1000 units = 0.01 lot)
                    # 100000 / 100 = 1000 units
                    # 1000 units / 100000 (units/lot) = 0.01 Lots
                    # Fator total: 100 * 100000 = 10,000,000
                    
                    digits = s.digits if hasattr(s, 'digits') else 5
                    pip_pos = s.pipPosition if hasattr(s, 'pipPosition') else (digits - 1)
                    self.symbol_info = {
                        'point': 10 ** (-digits),
                        'digits': digits,
                        'pip_value': 10.0,  
                        'spread_points': getattr(s, 'spreadMin', 7) if hasattr(s, 'spreadMin') else 7,
                        'min_lot': s.minVolume / 10000000.0 if hasattr(s, 'minVolume') else 0.01,
                        'max_lot': s.maxVolume / 10000000.0 if hasattr(s, 'maxVolume') else 100.0,
                        'lot_step': s.stepVolume / 10000000.0 if hasattr(s, 'stepVolume') else 0.01,
                    }
                    print(f"   Symbol Info: digits={digits}, spread={self.symbol_info['spread_points']}, min_lot={self.symbol_info['min_lot']}")
                else:
                    print("⚠️ Symbol Details vazio!")
                
                self.request_bars()
                # self._connected.set()

            # 4. Resposta de Barras
            elif message.payloadType == ProtoOAGetTrendbarsRes().payloadType:
                res = Protobuf.extract(message)
                
                if hasattr(res, 'trendbar') and res.trendbar:
                    print(f"   Recebido chunk com {len(res.trendbar)} barras...")
                    for tb in res.trendbar:
                        # Parse básico
                        low = tb.low / 100000.0 if tb.low else 0
                        bar_time = int(tb.utcTimestampInMinutes * 60)
                        
                        self.bars.append({
                            'time': str(datetime.utcfromtimestamp(bar_time)),
                            'open': low + (tb.deltaOpen / 100000.0 if hasattr(tb, 'deltaOpen') else 0),
                            'high': low + (tb.deltaHigh / 100000.0 if hasattr(tb, 'deltaHigh') else 0),
                            'low': low,
                            'close': low + (tb.deltaClose / 100000.0 if hasattr(tb, 'deltaClose') else 0),
                            'volume': tb.volume
                        })
                    
                    # Avança cursor
                    # Precisamos saber até onde fomos. O chunk cobre até res.timestamp?
                    # A logica do notebook usa chunk_to explicito. Aqui vamos simplificar incrementando
                    # Assumindo que o pedido foi atendido
                    # O request foi: from current_from -> current_from + 7 dias
                    
                    self.current_from += (7 * 86400 * 1000) # +1 semana
                    if self.current_from < self.to_timestamp:
                        # Pequeno delay para evitar flood
                        time.sleep(0.2)
                        self.request_bars()
                    else:
                        self._done.set()
                else:
                    print("   Chunk vazio (fim dos dados ou erro).")
                    self._done.set()

            elif message.payloadType == ProtoOAErrorRes().payloadType:
                err = Protobuf.extract(message)
                self._error = f"API Error: {err.errorCode} - {err.description}"
                self._done.set()

        except Exception as e:
            self._error = str(e)
            self._done.set()

    def request_bars(self):
        chunk_to = min(self.current_from + (7 * 86400 * 1000), self.to_timestamp)
        
        print(f"📥 Baixando: {datetime.utcfromtimestamp(self.current_from/1000)} -> {datetime.utcfromtimestamp(chunk_to/1000)}")
        
        msg = ProtoOAGetTrendbarsReq()
        msg.ctidTraderAccountId = CTRADER_ACCOUNT_ID
        msg.symbolId = self.symbol_id
        msg.period = TIMEFRAME_TO_PERIOD[TIMEFRAME]
        msg.fromTimestamp = int(self.current_from)
        msg.toTimestamp = int(chunk_to)
        
        self.client.send(msg)

if __name__ == "__main__":
    dl = DataDownloader()
    dl.start()
