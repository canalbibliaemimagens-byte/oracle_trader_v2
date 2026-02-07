import os
import sys
import json
import threading
import time
from datetime import datetime
from twisted.internet import reactor
from ctrader_open_api import Client, TcpProtocol, EndPoints, Protobuf
from ctrader_open_api.messages.OpenApiMessages_pb2 import *
from ctrader_open_api.messages.OpenApiModelMessages_pb2 import *
from dotenv import load_dotenv
from google.protobuf.json_format import MessageToDict

# Carrega .env
load_dotenv()

CTRADER_CLIENT_ID = os.getenv("CTRADER_CLIENT_ID")
CTRADER_CLIENT_SECRET = os.getenv("CTRADER_CLIENT_SECRET")
CTRADER_ACCESS_TOKEN = os.getenv("CTRADER_ACCESS_TOKEN")
CTRADER_ACCOUNT_ID = os.getenv("CTRADER_ACCOUNT_ID")
ENVIRONMENT = os.getenv("CTRADER_ENVIRONMENT", "demo").lower()

if not all([CTRADER_CLIENT_ID, CTRADER_CLIENT_SECRET, CTRADER_ACCESS_TOKEN, CTRADER_ACCOUNT_ID]):
    print("❌ Erro: Credenciais incompletas no .env")
    sys.exit(1)

CTRADER_ACCOUNT_ID = int(CTRADER_ACCOUNT_ID)
HOST = EndPoints.PROTOBUF_LIVE_HOST if ENVIRONMENT == "live" else EndPoints.PROTOBUF_DEMO_HOST
PORT = EndPoints.PROTOBUF_PORT

TARGET_SYMBOL = sys.argv[1] if len(sys.argv) > 1 else "USDJPY"

class SymbolSpecsDumper:
    def __init__(self):
        self.client = Client(HOST, PORT, TcpProtocol)
        self.client.setConnectedCallback(self.connected)
        self.client.setDisconnectedCallback(self.disconnected)
        self.client.setMessageReceivedCallback(self.message_received)
        self._done = threading.Event()
        self._error = None
        self.symbol_id = None

    def start(self):
        print(f"🌍 Ambiente: {ENVIRONMENT.upper()} ({HOST}:{PORT})")
        print(f"🔍 Buscando especificações para: {TARGET_SYMBOL}")
        
        self._reactor_thread = threading.Thread(target=reactor.run, kwargs={'installSignalHandlers': False}, daemon=True)
        self._reactor_thread.start()
        reactor.callFromThread(self.client.startService)
        
        self._done.wait(timeout=30)
        
        if self._error:
            print(f"\n❌ Erro: {self._error}")
        
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
            if message.payloadType == ProtoOAApplicationAuthRes().payloadType:
                print("✅ App Auth OK. Autenticando Conta...")
                msg = ProtoOAAccountAuthReq()
                msg.accessToken = CTRADER_ACCESS_TOKEN
                msg.ctidTraderAccountId = CTRADER_ACCOUNT_ID
                client.send(msg)

            elif message.payloadType == ProtoOAAccountAuthRes().payloadType:
                print("✅ Conta Autenticada. Buscando Symbols List...")
                msg = ProtoOASymbolsListReq()
                msg.ctidTraderAccountId = CTRADER_ACCOUNT_ID
                client.send(msg)

            elif message.payloadType == ProtoOASymbolsListRes().payloadType:
                res = Protobuf.extract(message)
                for sym in res.symbol:
                    name = sym.symbolName if hasattr(sym, 'symbolName') else str(sym.symbolId)
                    if name == TARGET_SYMBOL:
                        self.symbol_id = sym.symbolId
                        print(f"✅ ID encontrado: {self.symbol_id}. Baixando detalhes completos...")
                        
                        req = ProtoOASymbolByIdReq()
                        req.ctidTraderAccountId = CTRADER_ACCOUNT_ID
                        req.symbolId.append(self.symbol_id)
                        client.send(req)
                        return
                
                self._error = f"Símbolo {TARGET_SYMBOL} não encontrado na lista."
                self._done.set()

            elif message.payloadType == ProtoOASymbolByIdRes().payloadType:
                res = Protobuf.extract(message)
                if not res.symbol:
                    self._error = "Detalhes do símbolo vazios."
                    self._done.set()
                    return

                s = res.symbol[0]
                
                # Converte para dicionário legível
                data = MessageToDict(s)
                
                # Cálculos de conveniência
                min_vol_raw = float(data.get('minVolume', 0))
                step_vol_raw = float(data.get('stepVolume', 0))
                
                # Fator de conversão dinâmico (Universal)
                # A API fornece 'lotSize' (em centavos/units raw). 
                # A fórmula correta é: Lotes = VolumeRaw / LotSizeRaw
                
                lot_raw_size = float(data.get('lotSize', 10000000))
                
                data['_calculated'] = {
                    'min_lot_v2': min_vol_raw / lot_raw_size,
                    'step_lot_v2': step_vol_raw / lot_raw_size,
                    'raw_min_volume': min_vol_raw
                }

                # Cálculos de Valor do Ponto (Quote Currency)
                point_size = 10 ** (-s.digits)
                
                # Conversão para Unidades "Reais" (Currency Units)
                # A API usa centavos/raw? Depende do asset. Forex geralmente é Units.
                # Mas vimos que minVolume 100,000 era 0.01 lot (1000 units).
                # Entao Raw / 100 = Units.
                
                lot_units = lot_raw_size / 100.0 
                
                # Valor de 1 Ponto por lote Padrão (na moeda de cotação - Quote Ccy)
                value_per_point_per_lot = lot_units * point_size
                
                data['_calculated']['point_size'] = point_size
                data['_calculated']['lot_units'] = lot_units
                data['_calculated']['value_per_point_quote_ccy'] = value_per_point_per_lot

                # Salva em arquivo
                filename = f"specs_{TARGET_SYMBOL}.json"
                with open(filename, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=4)
                
                print(f"\n📋 Especificações completas salvas em: {filename}")
                
                # Salva Tabela em Arquivo (para evitar erro de encoding no console do Windows)
                table_file = f"specs_{TARGET_SYMBOL}.txt"
                with open(table_file, "w", encoding="utf-8") as f:
                    f.write(f"\n{'='*60}\n")
                    f.write(f"ESPECIFICAÇÕES TÉCNICAS: {TARGET_SYMBOL}\n")
                    f.write(f"{'='*60}\n")
                    
                    def write_row(label, value):
                        f.write(f"{label:<30} | {str(value):<25}\n")

                    f.write(f"\n--- IDENTIFICAÇÃO ---\n")
                    write_row("Symbol ID", s.symbolId)
                    write_row("Digits", s.digits)
                    write_row("Point Size", f"{point_size:.{s.digits}f}") # NEW
                    write_row("Pip Position", s.pipPosition)

                    f.write(f"\n--- VOLUMES (Raw Units) ---\n")
                    write_row("Min Volume", data.get('minVolume'))
                    write_row("Step Volume", data.get('stepVolume'))
                    write_row("Max Volume", data.get('maxVolume'))
                    write_row("Lot Size (Raw)", data.get('lotSize')) # NEW

                    f.write(f"\n--- VALUS DO PONTO (Estimado) ---\n") # EMOJI REMOVED
                    write_row("1 Lot (Units)", f"{lot_units:,.0f}")
                    write_row("Value per Point (1 Lot)", f"{value_per_point_per_lot:.5f} (Quote Ccy)")
                    
                    f.write(f"\n--- LOTES (Calculado / 10M) ---\n")
                    write_row("Min Lot", f"{data['_calculated']['min_lot_v2']:.2f}")
                    write_row("Step Lot", f"{data['_calculated']['step_lot_v2']:.2f}")

                    f.write(f"\n--- CUSTOS & SWAPS ---\n")
                    write_row("Commission", data.get('commission'))
                    write_row("Comm. Type", data.get('commissionType'))
                    write_row("Min Commission", data.get('minCommission'))
                    write_row("Swap Long", data.get('swapLong'))
                    write_row("Swap Short", data.get('swapShort'))
                    write_row("Swap 3-Days", data.get('swapRollover3Days'))

                    f.write(f"\n--- AGENDAMENTO ---\n")
                    write_row("Timezone", data.get('scheduleTimeZone'))
                    f.write(f"{'='*60}\n")
                
                print(f"📋 Tabela salva em: {table_file}")
                # print(open(table_file, 'r', encoding='utf-8').read()) # Opcional: tentar imprimir se der
                
                self._done.set()

            elif message.payloadType == ProtoOAErrorRes().payloadType:
                err = Protobuf.extract(message)
                self._error = f"API Error: {err.errorCode} - {err.description}"
                self._done.set()

        except Exception as e:
            self._error = str(e)
            self._done.set()

if __name__ == "__main__":
    dumper = SymbolSpecsDumper()
    dumper.start()
