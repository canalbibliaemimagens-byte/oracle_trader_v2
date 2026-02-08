"""
📥 Download OHLCV via cTrader → Upload para Supabase
=====================================================
Script LOCAL que baixa dados históricos do cTrader e salva em
um bucket dedicado no Supabase ("oracle_ohlcv").

Roda na máquina local (sem GPU), economizando recursos do Kaggle/Colab.

Uso individual:
    python download_ohlcv_to_supabase.py EURUSD -tf M15 --years 3

Uso por categoria (baixa todos os ativos de uma vez):
    python download_ohlcv_to_supabase.py --category forex -tf M15 --years 3
    python download_ohlcv_to_supabase.py --category indices -tf M15 --years 2
    python download_ohlcv_to_supabase.py --category commodities -tf M15 --years 2

Listar categorias:
    python download_ohlcv_to_supabase.py --list-categories

Dependências:
    pip install python-dotenv twisted pyopenssl service_identity
    pip install ctrader-open-api>=0.9.0 protobuf==3.20.1
    pip install supabase pandas pyarrow

Bucket Supabase: oracle_ohlcv
Formato: {SYMBOL}_{TIMEFRAME}.parquet  (compacto e rápido)
"""

import os
import sys
import argparse
import hashlib
import threading
import time
import io
from datetime import datetime, timedelta, timezone

import pandas as pd
from dotenv import load_dotenv
from twisted.internet import reactor
from ctrader_open_api import Client, TcpProtocol, EndPoints, Protobuf
from ctrader_open_api.messages.OpenApiMessages_pb2 import *
from ctrader_open_api.messages.OpenApiModelMessages_pb2 import *

# ─── Carregar .env ───────────────────────────────────────────────────────────
load_dotenv()

CTRADER_CLIENT_ID = os.getenv("CTRADER_CLIENT_ID")
CTRADER_CLIENT_SECRET = os.getenv("CTRADER_CLIENT_SECRET")
CTRADER_ACCESS_TOKEN = os.getenv("CTRADER_ACCESS_TOKEN")
CTRADER_ACCOUNT_ID = os.getenv("CTRADER_ACCOUNT_ID")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
ENVIRONMENT = os.getenv("CTRADER_ENVIRONMENT", "demo").lower()

# Validação
required = {
    "CTRADER_CLIENT_ID": CTRADER_CLIENT_ID,
    "CTRADER_CLIENT_SECRET": CTRADER_CLIENT_SECRET,
    "CTRADER_ACCESS_TOKEN": CTRADER_ACCESS_TOKEN,
    "CTRADER_ACCOUNT_ID": CTRADER_ACCOUNT_ID,
    "SUPABASE_URL": SUPABASE_URL,
    "SUPABASE_KEY": SUPABASE_KEY,
}
missing = [k for k, v in required.items() if not v]
if missing:
    print(f"❌ Variáveis faltando no .env: {', '.join(missing)}")
    sys.exit(1)

CTRADER_ACCOUNT_ID = int(CTRADER_ACCOUNT_ID)

HOST = EndPoints.PROTOBUF_LIVE_HOST if ENVIRONMENT == "live" else EndPoints.PROTOBUF_DEMO_HOST
PORT = EndPoints.PROTOBUF_PORT

# ─── Mapeamento de Timeframes ────────────────────────────────────────────────
TIMEFRAME_TO_PERIOD = {
    "M1": 1, "M2": 2, "M3": 3, "M4": 4, "M5": 5, "M10": 6, "M15": 7,
    "M30": 8, "H1": 9, "H4": 10, "H12": 11, "D1": 12, "W1": 13, "MN1": 14,
}

BUCKET_NAME = "oracle_ohlcv"


class OHLCVDownloader:
    """Baixa dados OHLCV via cTrader e faz upload para Supabase."""

    def __init__(self, symbol: str, timeframe: str, from_ms: int, to_ms: int):
        self.symbol = symbol
        self.timeframe = timeframe
        self.from_ms = from_ms
        self.to_ms = to_ms

        self.client = Client(HOST, PORT, TcpProtocol)
        self.client.setConnectedCallback(self.connected)
        self.client.setDisconnectedCallback(self.disconnected)
        self.client.setMessageReceivedCallback(self.message_received)

        self._done = threading.Event()
        self._error = None
        self.symbol_id = None
        self.symbol_info = {}
        self.bars = []
        self.current_from = from_ms

    def start(self):
        print(f"🌐 Ambiente: {ENVIRONMENT.upper()} ({HOST}:{PORT})")
        print(f"📊 {self.symbol} {self.timeframe}")
        print(f"📅 {datetime.utcfromtimestamp(self.from_ms/1000):%Y-%m-%d} → "
              f"{datetime.utcfromtimestamp(self.to_ms/1000):%Y-%m-%d}")

        # Reactor singleton: só inicia na primeira chamada
        if not reactor.running:
            self._reactor_thread = threading.Thread(
                target=reactor.run, kwargs={'installSignalHandlers': False}, daemon=True
            )
            self._reactor_thread.start()
            time.sleep(0.5)  # Dar tempo para o reactor iniciar

        reactor.callFromThread(self.client.startService)

        # Aguarda download completo (timeout generoso para 3 anos de dados)
        self._done.wait(timeout=300)

        if self._error:
            print(f"\n❌ Erro: {self._error}")
            self.stop()
            return None

        print(f"\n✅ Download concluído! {len(self.bars):,} barras")
        self.stop()

        if not self.bars:
            print("⚠️ Nenhuma barra recebida.")
            return None

        # Montar DataFrame
        df = pd.DataFrame(self.bars)
        df = df.sort_values('datetime').drop_duplicates(subset='datetime').reset_index(drop=True)
        print(f"   Após dedup: {len(df):,} barras")
        print(f"   Período: {df['datetime'].iloc[0]} → {df['datetime'].iloc[-1]}")

        return df

    def stop(self):
        try:
            reactor.callFromThread(self.client.stopService)
        except Exception:
            pass

    def connected(self, client):
        print("   ✅ TCP/SSL conectado. Autenticando...")
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
            # App Auth
            if message.payloadType == ProtoOAApplicationAuthRes().payloadType:
                print("   ✅ App Auth OK")
                msg = ProtoOAAccountAuthReq()
                msg.accessToken = CTRADER_ACCESS_TOKEN
                msg.ctidTraderAccountId = CTRADER_ACCOUNT_ID
                client.send(msg)

            # Account Auth
            elif message.payloadType == ProtoOAAccountAuthRes().payloadType:
                print(f"   ✅ Conta {CTRADER_ACCOUNT_ID} autenticada. Buscando símbolo...")
                msg = ProtoOASymbolsListReq()
                msg.ctidTraderAccountId = CTRADER_ACCOUNT_ID
                client.send(msg)

            # Symbols List
            elif message.payloadType == ProtoOASymbolsListRes().payloadType:
                res = Protobuf.extract(message)
                for sym in res.symbol:
                    name = sym.symbolName if hasattr(sym, 'symbolName') else str(sym.symbolId)
                    if name == self.symbol:
                        self.symbol_id = sym.symbolId
                        break

                if self.symbol_id:
                    print(f"   ✅ Símbolo {self.symbol} (ID: {self.symbol_id}). Baixando barras...")
                    self._request_bars()
                else:
                    self._error = f"Símbolo {self.symbol} não encontrado"
                    self._done.set()

            # Trendbars Response
            elif message.payloadType == ProtoOAGetTrendbarsRes().payloadType:
                res = Protobuf.extract(message)

                if hasattr(res, 'trendbar') and res.trendbar:
                    count = len(res.trendbar)
                    for tb in res.trendbar:
                        low = tb.low / 100000.0 if tb.low else 0
                        bar_time = int(tb.utcTimestampInMinutes * 60)

                        self.bars.append({
                            'datetime': str(datetime.utcfromtimestamp(bar_time)),
                            'open': low + (tb.deltaOpen / 100000.0 if hasattr(tb, 'deltaOpen') else 0),
                            'high': low + (tb.deltaHigh / 100000.0 if hasattr(tb, 'deltaHigh') else 0),
                            'low': low,
                            'close': low + (tb.deltaClose / 100000.0 if hasattr(tb, 'deltaClose') else 0),
                            'volume': tb.volume if hasattr(tb, 'volume') else 0,
                        })

                    # Avança cursor (+7 dias)
                    self.current_from += (7 * 86400 * 1000)
                    progress = min(100, (self.current_from - self.from_ms) / (self.to_ms - self.from_ms) * 100)
                    print(f"   📥 {len(self.bars):,} barras ({progress:.0f}%)", end="\r")

                    if self.current_from < self.to_ms:
                        time.sleep(0.15)  # Rate limiting
                        self._request_bars()
                    else:
                        print()  # Nova linha após progresso
                        self._done.set()
                else:
                    # Chunk vazio — tenta avançar
                    self.current_from += (7 * 86400 * 1000)
                    if self.current_from < self.to_ms:
                        time.sleep(0.15)
                        self._request_bars()
                    else:
                        print()
                        self._done.set()

            # Error
            elif message.payloadType == ProtoOAErrorRes().payloadType:
                err = Protobuf.extract(message)
                self._error = f"API Error: {err.errorCode} - {err.description}"
                self._done.set()

        except Exception as e:
            self._error = str(e)
            self._done.set()

    def _request_bars(self):
        chunk_to = min(self.current_from + (7 * 86400 * 1000), self.to_ms)
        msg = ProtoOAGetTrendbarsReq()
        msg.ctidTraderAccountId = CTRADER_ACCOUNT_ID
        msg.symbolId = self.symbol_id
        msg.period = TIMEFRAME_TO_PERIOD[self.timeframe]
        msg.fromTimestamp = int(self.current_from)
        msg.toTimestamp = int(chunk_to)
        self.client.send(msg)


def upload_to_supabase(df: pd.DataFrame, symbol: str, timeframe: str):
    """Faz upload do DataFrame como Parquet para o Supabase Storage com retry."""
    from supabase import create_client

    sb = create_client(SUPABASE_URL, SUPABASE_KEY)

    filename = f"{symbol}_{timeframe}.parquet"
    remote_path = f"{symbol}_{timeframe}/{filename}"

    # Serializa para Parquet em memória
    buffer = io.BytesIO()
    df.to_parquet(buffer, index=False, engine='pyarrow')
    parquet_bytes = buffer.getvalue()

    # Hash local
    local_hash = hashlib.md5(parquet_bytes).hexdigest()

    print(f"\n📤 Upload: {filename} ({len(parquet_bytes)/1024/1024:.2f} MB)")
    print(f"   Bucket: {BUCKET_NAME}")
    print(f"   Path: {remote_path}")

    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            if attempt > 1:
                wait = attempt * 3
                print(f"   🔄 Tentativa {attempt}/{max_retries} (aguardando {wait}s)...")
                time.sleep(wait)
                # Recriar client para nova conexão
                sb = create_client(SUPABASE_URL, SUPABASE_KEY)

            sb.storage.from_(BUCKET_NAME).upload(
                path=remote_path,
                file=parquet_bytes,
                file_options={"content-type": "application/octet-stream", "upsert": "true"}
            )
            print(f"   ✅ Upload concluído")

            # Verificação
            remote_data = sb.storage.from_(BUCKET_NAME).download(remote_path)
            remote_hash = hashlib.md5(remote_data).hexdigest()

            if local_hash == remote_hash:
                print(f"   ✅ Integridade OK ({local_hash[:8]}...)")
            else:
                print(f"   ❌ Hash mismatch! Local={local_hash} Remoto={remote_hash}")
            break  # Sucesso, sair do loop

        except Exception as e:
            err_str = str(e).lower()
            if "not found" in err_str or "404" in err_str:
                print(f"   ⚠️ Bucket '{BUCKET_NAME}' não encontrado. Criando...")
                try:
                    sb.storage.create_bucket(BUCKET_NAME, options={"public": False})
                    print(f"   ✅ Bucket criado. Tentando upload novamente...")
                    sb.storage.from_(BUCKET_NAME).upload(
                        path=remote_path,
                        file=parquet_bytes,
                        file_options={"content-type": "application/octet-stream", "upsert": "true"}
                    )
                    print(f"   ✅ Upload concluído")
                    break
                except Exception as e2:
                    print(f"   ❌ Erro ao criar bucket: {e2}")
            elif attempt < max_retries:
                print(f"   ⚠️ Erro (tentativa {attempt}): {e}")
            else:
                print(f"   ❌ Falhou após {max_retries} tentativas: {e}")

    # Também salva localmente como backup
    local_path = f"data_{symbol}_{timeframe}.parquet"
    df.to_parquet(local_path, index=False)
    print(f"   📁 Backup local: {local_path}")


# ─── Catálogo de Categorias ──────────────────────────────────────────────────
CATEGORIES = {
    "forex": [
        "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD",
        "NZDUSD", "USDCHF", "EURGBP", "EURJPY", "GBPJPY",
        # Validação
        "AUDCHF", "CADCHF", "EURAUD",
    ],
    "indices": [
        "US500", "US30", "US100", "GER40", "UK100",
        "JP225", "FRA40",
        # Validação
        "AUS200", "ESP35",
    ],
    "commodities": [
        "XAUUSD", "XAGUSD", "USOIL", "UKOIL", "NATGAS",
        # Validação
        "COPPER", "PLATINUM",
    ],
}


def download_single(symbol, timeframe, from_ms, to_ms, no_upload=False):
    """Baixa um único símbolo e faz upload."""
    downloader = OHLCVDownloader(symbol, timeframe, from_ms, to_ms)
    df = downloader.start()

    if df is None or df.empty:
        print(f"❌ {symbol}: Sem dados.")
        return False

    if not no_upload:
        upload_to_supabase(df, symbol, timeframe)
    else:
        local_path = f"data_{symbol}_{timeframe}.parquet"
        df.to_parquet(local_path, index=False)
        print(f"   📁 Salvo: {local_path}")

    return True


def main():
    parser = argparse.ArgumentParser(
        description="Baixa OHLCV do cTrader e salva no Supabase",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Modos de uso:

  Ativo individual:
    python download_ohlcv_to_supabase.py EURUSD -tf M15 --years 3

  Categoria inteira (baixa todos os ativos de uma vez):
    python download_ohlcv_to_supabase.py --category forex -tf M15 --years 3
    python download_ohlcv_to_supabase.py --category indices -tf M15 --years 2
    python download_ohlcv_to_supabase.py --category commodities -tf M15 --years 2

  Listar categorias:
    python download_ohlcv_to_supabase.py --list-categories

Categorias disponíveis:
  forex:       EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD, NZDUSD, USDCHF,
               EURGBP, EURJPY, GBPJPY + AUDCHF, CADCHF, EURAUD (validação)
  indices:     US500, US30, US100, GER40, UK100, JP225, FRA40 + AUS200, ESP35
  commodities: XAUUSD, XAGUSD, USOIL, UKOIL, NATGAS + COPPER, PLATINUM
        """
    )
    parser.add_argument("symbol", nargs="?", default=None,
                        help="Símbolo individual (ex: EURUSD). Ignorado se --category usado.")
    parser.add_argument("-tf", "--timeframe", default=None,
                        choices=list(TIMEFRAME_TO_PERIOD.keys()),
                        help="Timeframe (ex: M15, H1)")

    group = parser.add_mutually_exclusive_group()
    group.add_argument("--years", type=float, help="Período em anos")
    group.add_argument("--months", type=int, help="Período em meses")
    group.add_argument("--days", type=int, help="Período em dias")

    parser.add_argument("--category", choices=list(CATEGORIES.keys()),
                        help="Baixar todos os ativos de uma categoria")
    parser.add_argument("--list-categories", action="store_true",
                        help="Listar categorias e seus ativos")
    parser.add_argument("--no-upload", action="store_true",
                        help="Apenas salva localmente, não faz upload")
    parser.add_argument("--end-date", type=str, default=None,
                        help="Data final (YYYY-MM-DD), padrão=hoje")

    args = parser.parse_args()

    # Listar categorias
    if args.list_categories:
        print("=" * 60)
        print("📋 CATEGORIAS DISPONÍVEIS")
        print("=" * 60)
        for cat, symbols in CATEGORIES.items():
            print(f"\n  {cat.upper()} ({len(symbols)} ativos):")
            for s in symbols:
                print(f"    - {s}")
        return

    # Validar argumentos
    if not args.category and not args.symbol:
        parser.error("Informe um símbolo ou use --category")

    if not args.timeframe:
        parser.error("Timeframe é obrigatório (ex: M15)")

    if not args.years and not args.months and not args.days:
        parser.error("Informe o período: --years, --months ou --days")

    # Calcular período
    if args.end_date:
        end = datetime.strptime(args.end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    else:
        end = datetime.now(timezone.utc)

    if args.years:
        start = end - timedelta(days=int(args.years * 365.25))
    elif args.months:
        start = end - timedelta(days=args.months * 30)
    else:
        start = end - timedelta(days=args.days)

    from_ms = int(start.timestamp() * 1000)
    to_ms = int(end.timestamp() * 1000)

    # Montar lista de símbolos
    if args.category:
        symbols = CATEGORIES[args.category]
        print("=" * 60)
        print(f"📥 DOWNLOAD EM LOTE: {args.category.upper()}")
        print(f"   {len(symbols)} ativos | {args.timeframe}")
        print(f"   {start.strftime('%Y-%m-%d')} → {end.strftime('%Y-%m-%d')}")
        print("=" * 60)

        ok, fail = 0, 0
        for i, symbol in enumerate(symbols, 1):
            print(f"\n{'─'*60}")
            print(f"[{i}/{len(symbols)}] {symbol}")
            print(f"{'─'*60}")
            try:
                success = download_single(symbol, args.timeframe, from_ms, to_ms, args.no_upload)
                if success:
                    ok += 1
                else:
                    fail += 1
            except Exception as e:
                print(f"❌ {symbol}: {e}")
                fail += 1

            # Pausa entre downloads para não sobrecarregar a API
            if i < len(symbols):
                print("   ⏳ Aguardando 3s...")
                time.sleep(3)

        print(f"\n{'='*60}")
        print(f"🎉 LOTE CONCLUÍDO: {args.category.upper()}")
        print(f"   ✅ Sucesso: {ok}/{len(symbols)}")
        if fail > 0:
            print(f"   ❌ Falhas: {fail}/{len(symbols)}")
        print(f"{'='*60}")

    else:
        # Download individual
        print("=" * 60)
        print(f"📥 ORACLE OHLCV DOWNLOADER")
        print("=" * 60)

        success = download_single(args.symbol, args.timeframe, from_ms, to_ms, args.no_upload)
        if not success:
            sys.exit(1)

        print(f"\n{'='*60}")
        print(f"🎉 Concluído: {args.symbol} {args.timeframe}")
        print(f"{'='*60}")


if __name__ == "__main__":
    main()
