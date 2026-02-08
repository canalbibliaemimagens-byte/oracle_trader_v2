"""
eXplorador cTrader (Refactored & Enhanced)
==========================================
Script principal para exploração e diagnóstico da API cTrader.
Usa o novo conector (Twisted Raw) para buscar:
- Dados da Conta (Aguarda sync)
- Posições Abertas
- Histórico de Transações (Deals) - Detalhado

Uso:
    python scripts/ctrader_explorer.py
"""
import asyncio
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# Add project root
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load Env
from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("Explorer")

def print_header(title):
    print("\n" + "=" * 80)
    print(f" {title}")
    print("=" * 80)

async def main():
    print_header("INITIALIZING ORACLE TRADER EXPLORER")
    
    config = {
        "client_id": os.getenv("CTRADER_CLIENT_ID"),
        "client_secret": os.getenv("CTRADER_CLIENT_SECRET"),
        "access_token": os.getenv("CTRADER_ACCESS_TOKEN"),
        "account_id": os.getenv("CTRADER_ACCOUNT_ID"),
        "environment": "demo"
    }

    from connector.ctrader.client import CTraderConnector
    connector = CTraderConnector(config)
    
    print("* Connecting to cTrader (Raw Protocol)...")
    if await connector.connect():
        print("OK Connected! Waiting for data sync...")
        
        # ACTIVE WAIT FOR ACCOUNT DATA
        for _ in range(10):
            acc = await connector.get_account()
            if acc.balance > 0:
                break
            print(".", end="", flush=True)
            await asyncio.sleep(1)
        print()
        
        # 1. Account Info
        print_header("ACCOUNT INFO")
        acc = await connector.get_account()
        print(f"   ID:          {config['account_id']}")
        print(f"   Balance:     ${acc.balance:,.2f}")
        print(f"   Equity:      ${acc.equity:,.2f}")
        print(f"   Margin Used: ${acc.margin:,.2f}")
        print(f"   Free Margin: ${acc.free_margin:,.2f}")
        
        # 2. Open Positions
        pos = await connector.get_positions()
        print_header(f"OPEN POSITIONS ({len(pos)})")
        if pos:
            # Table Header
            print(f"   {'TICKET':<10} {'SYMBOL':<8} {'DIR':<4} {'VOL':<6} {'PRICE':<10} {'PnL':<10} {'SWAP':<8} {'COMM':<8}")
            print("   " + "-" * 70)
            for p in pos:
                pnl_str = f"${p.pnl:.2f}"
                dir_str = "BUY" if p.direction == 1 else "SELL"
                # TODO: Retrieve swap/comm for open positions if available in model
                # Current Position model has simple fields.
                print(f"   {p.ticket:<10} {p.symbol:<8} {dir_str:<4} {p.volume:<6.2f} {p.current_price:<10.5f} {pnl_str:<10}")
        else:
            print("   (No open positions)")
            
        # 3. Deal History (30 Days)
        print_header("DEAL HISTORY (Last 30 Days)")
        since = datetime.now() - timedelta(days=30)
        print(f"   Fetching since: {since.strftime('%Y-%m-%d')}")
        
        deals = await connector.get_order_history(since)
        print(f"   Found {len(deals)} deals.")
        
        if deals:
            print("\n   Recent Deals (Top 50):")
            # Detailed Columns
            # Time, DealID, OrderID, Sym, Type, Vol, Price, Comm, Swap, Profit
            header = f"   {'TIME':<12} {'DEAL ID':<10} {'ORDER ID':<10} {'SYM':<6} {'TYP':<4} {'VOL':<5} {'PRICE':<9} {'COMM':<7} {'SWAP':<7} {'PROFIT':<9}"
            print(header)
            print("   " + "-" * len(header))
            
            # Sort by timestamp desc
            deals.sort(key=lambda x: x['timestamp'], reverse=True)
            
            for d in deals[:50]:
                ts = datetime.fromtimestamp(d['timestamp']).strftime('%m-%d %H:%M')
                profit = f"${d['pnl']:,.2f}" if d['pnl'] else "-"
                comm = f"{d['commission']:.2f}" if d['commission'] else "-"
                swap = f"{d['swap']:.2f}" if d['swap'] else "-"
                
                line = f"   {ts:<12} {d['id']:<10} {d['order_id']:<10} {d['symbol']:<6} {d['type']:<4} {d['volume']:<5.2f} {d['entry_price']:<9.5f} {comm:<7} {swap:<7} {profit:<9}"
                print(line)
                
        # 4. Disconnect
        print("\nBye Disconnecting...")
        await connector.disconnect()
        
    else:
        print("Error Failed to connect.")

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    try:
        import twisted.internet.asyncioreactor as asyncioreactor
        if 'twisted.internet.reactor' not in sys.modules:
            asyncioreactor.install()
    except Exception as e:
        print(f"Reactor warning: {e}")

    from twisted.internet import reactor
    loop = asyncio.get_event_loop()
    
    async def runner():
        try:
            await main()
        finally:
            print("\n* Stopping Reactor...")
            if reactor.running:
                reactor.stop()

    loop.create_task(runner())
    reactor.run()
