"""
cTrader Explorer — RAW Implementation v3 (Final)
================================================
"""
import os
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

CLIENT_ID = os.getenv("CTRADER_CLIENT_ID")
CLIENT_SECRET = os.getenv("CTRADER_CLIENT_SECRET")
ACCESS_TOKEN = os.getenv("CTRADER_ACCESS_TOKEN")
ACCOUNT_ID = int(os.getenv("CTRADER_ACCOUNT_ID", "0"))
HOST = "demo.ctraderapi.com"
PORT = 5035

from twisted.internet import protocol, reactor, ssl
# Import correct modules based on check_proto.py findings
from ctrader_open_api.messages import OpenApiMessages_pb2 as msg
from ctrader_open_api.messages import OpenApiModelMessages_pb2 as mdl
from ctrader_open_api.messages import OpenApiCommonMessages_pb2 as common

def fmt_money(v): return f"${v/100:.2f}" if v else "$0.00"
def fmt_vol(u): return f"{u/100000:.2f} lots"

class CTraderProtocol(protocol.Protocol):
    def __init__(self):
        self._buffer = b""
        self._msg_len = None

    def connectionMade(self):
        print("✅ TCP/SSL Connected. Sending AppAuth...")
        self.send_proto(self._build_app_auth(), mdl.PROTO_OA_APPLICATION_AUTH_REQ)

    def dataReceived(self, data):
        self._buffer += data
        self._process_buffer()

    def _process_buffer(self):
        while True:
            if self._msg_len is None:
                if len(self._buffer) < 4:
                    return
                self._msg_len = struct.unpack(">I", self._buffer[:4])[0]
                self._buffer = self._buffer[4:]

            if len(self._buffer) < self._msg_len:
                return

            msg_bytes = self._buffer[:self._msg_len]
            self._buffer = self._buffer[self._msg_len:]
            self._msg_len = None
            
            try:
                self._handle_message(msg_bytes)
            except Exception as e:
                print(f"❌ Error handling frame: {e}")


    def _handle_message(self, data):
        wrapper = common.ProtoMessage()
        wrapper.ParseFromString(data)
        
        pt = wrapper.payloadType
        payload = wrapper.payload
        
        if pt == mdl.PROTO_OA_APPLICATION_AUTH_RES:
            print("✅ App Auth OK. Sending Account Auth...")
            self.send_proto(self._build_account_auth(), mdl.PROTO_OA_ACCOUNT_AUTH_REQ)
            
        elif pt == mdl.PROTO_OA_ACCOUNT_AUTH_RES:
            print(f"✅ Account Auth OK ({ACCOUNT_ID}). Fetching initial data...")
            self.send_proto(self._build_trader_req(), mdl.PROTO_OA_TRADER_REQ)
            self.send_proto(self._build_reconcile(), mdl.PROTO_OA_RECONCILE_REQ)
            self.send_proto(self._build_symbols_req(), mdl.PROTO_OA_SYMBOLS_LIST_REQ)
            self.send_proto(self._build_deals_req(), mdl.PROTO_OA_DEAL_LIST_REQ)
            
        elif pt == mdl.PROTO_OA_TRADER_RES:
            res = msg.ProtoOATraderRes()
            res.ParseFromString(payload)
            t = res.trader
            print(f"\n📊 ACCOUNT: {t.ctidTraderAccountId}")
            print(f"   Balance: {fmt_money(t.balance)}")
            print(f"   Equity: {fmt_money(t.balance)}") # Equity start = Balance, updated via spots
            print(f"   Lev: 1:{int(t.leverageInCents/100) if t.leverageInCents else '?'}")
            
        elif pt == mdl.PROTO_OA_RECONCILE_RES:
            res = msg.ProtoOAReconcileRes()
            res.ParseFromString(payload)
            print(f"\n📌 POSITIONS: {len(res.position)}")
            for p in res.position:
                d = "BUY" if p.tradeData.tradeSide == 1 else "SELL"
                print(f"   #{p.positionId} {d} {fmt_vol(p.tradeData.volume)} {p.tradeData.symbolId}")
                print(f"     Price: {p.price} | Comment: {p.tradeData.comment}")
            
        elif pt == mdl.PROTO_OA_SYMBOLS_LIST_RES:
             res = msg.ProtoOASymbolsListRes()
             res.ParseFromString(payload)
             print(f"\n📈 SYMBOLS: {len(res.symbol)} found.")
             # Subscribe to top 3 symbols for spot data test
             top_symbols = [s.symbolId for s in res.symbol if s.symbolName in ["EURUSD", "BTCUSD", "ETHUSD"]][:3]
             if top_symbols:
                 print(f"   >> Subscribing to spots for: {top_symbols}")
                 self.send_proto(self._build_subscribe_spots(top_symbols), mdl.PROTO_OA_SUBSCRIBE_SPOTS_REQ)
             
        elif pt == mdl.PROTO_OA_SUBSCRIBE_SPOTS_RES:
             res = msg.ProtoOASubscribeSpotsRes()
             res.ParseFromString(payload)
             print(f"\n✅ SUBSCRIBED to spots: {res.symbolId}")
             print("   (Listening for SpotEvents for 10 seconds...)")
             # Schedule disconnect
             reactor.callLater(10, self.disconnect_and_stop)

        elif pt == mdl.PROTO_OA_SPOT_EVENT:
             res = msg.ProtoOASpotEvent()
             res.ParseFromString(payload)
             # Decode prices (they are deltas or absolute if hasBid/Ask)
             bid = res.bid / 100000.0 if res.bid else 0
             ask = res.ask / 100000.0 if res.ask else 0
             print(f"   ⚡ SPOT {res.symbolId}: Bid={bid:.5f} Ask={ask:.5f}")
             
        elif pt == mdl.PROTO_OA_DEAL_LIST_RES:
             res = msg.ProtoOADealListRes()
             res.ParseFromString(payload)
             print(f"\n📜 DEALS: {len(res.deal)}")
             for d in res.deal[:3]:
                 print(f"   Deal #{d.dealId}: Profit={fmt_money(d.closePositionDetail.grossProfit if hasattr(d, 'closePositionDetail') else 0)}")
                 print(f"   Constraint: {d.comment if d.comment else 'No Comment'}")

        elif pt == mdl.PROTO_OA_ERROR_RES:
            res = msg.ProtoOAErrorRes()
            res.ParseFromString(payload)
            print(f"❌ ERROR: {res.description} ({res.errorCode})")

    def disconnect_and_stop(self):
        print("🛑 Updates finished. Disconnecting.")
        self.transport.loseConnection()

    def send_proto(self, protobuf_msg, payload_type):
        payload_bytes = protobuf_msg.SerializeToString()
        
        wrapper = common.ProtoMessage()
        wrapper.payloadType = payload_type
        wrapper.payload = payload_bytes
        
        wrapper_bytes = wrapper.SerializeToString()
        length_bytes = struct.pack(">I", len(wrapper_bytes))
        self.transport.write(length_bytes + wrapper_bytes)

    # Builders
    def _build_app_auth(self):
        m = msg.ProtoOAApplicationAuthReq()
        m.clientId = CLIENT_ID
        m.clientSecret = CLIENT_SECRET
        return m

    def _build_account_auth(self):
        m = msg.ProtoOAAccountAuthReq()
        m.accessToken = ACCESS_TOKEN
        m.ctidTraderAccountId = ACCOUNT_ID
        return m

    def _build_trader_req(self):
        m = msg.ProtoOATraderReq()
        m.ctidTraderAccountId = ACCOUNT_ID
        return m
        
    def _build_reconcile(self):
        m = msg.ProtoOAReconcileReq()
        m.ctidTraderAccountId = ACCOUNT_ID
        return m
        
    def _build_symbols_req(self):
         m = msg.ProtoOASymbolsListReq()
         m.ctidTraderAccountId = ACCOUNT_ID
         return m
         
    def _build_assets_req(self):
         m = msg.ProtoOAAssetListReq()
         m.ctidTraderAccountId = ACCOUNT_ID
         return m

    def _build_deals_req(self):
         from datetime import datetime, timedelta
         m = msg.ProtoOADealListReq()
         m.ctidTraderAccountId = ACCOUNT_ID
         now = datetime.utcnow()
         m.fromTimestamp = int((now - timedelta(days=1)).timestamp() * 1000)
         m.toTimestamp = int(now.timestamp() * 1000)
         return m

    def _build_subscribe_spots(self, symbol_ids):
        m = msg.ProtoOASubscribeSpotsReq()
        m.ctidTraderAccountId = ACCOUNT_ID
        m.symbolId.extend(symbol_ids)
        m.subscribeToSpotTimestamp = True
        return m


class CTraderFactory(protocol.ClientFactory):
    def buildProtocol(self, addr):
        return CTraderProtocol()
        
    def clientConnectionFailed(self, connector, reason):
        print(f"❌ Connection Failed: {reason}")
        reactor.stop()
        
    def clientConnectionLost(self, connector, reason):
        try: reactor.stop()
        except: pass

def main():
    print("🚀 Starting Raw Explorer...")
    reactor.connectSSL(HOST, PORT, CTraderFactory(), ssl.ClientContextFactory())
    reactor.run()

if __name__ == "__main__":
    if sys.platform == 'win32':
        import asyncio
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    main()
