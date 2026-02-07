"""Test HubClient connection to OTS Hub."""
import asyncio
import json
import websockets

async def test():
    print("🔌 Testando conexão com OTS Hub...")
    url = "ws://163.176.175.219:8000/ws/bot-v2"
    token = "OTS_HUB_TOKEN_0702226"
    print(f"   URL: {url}")
    
    try:
        async with websockets.connect(url) as ws:
            print("✅ WebSocket conectado!")
            
            # Auth - token DENTRO do payload
            auth_msg = {
                "type": "auth",
                "payload": {
                    "token": token,
                    "role": "bot"
                }
            }
            await ws.send(json.dumps(auth_msg))
            print("📤 Auth enviado")
            
            # Aguarda resposta
            response = await asyncio.wait_for(ws.recv(), timeout=5)
            data = json.loads(response)
            print(f"📥 Resposta: {data}")
            
            if data.get("type") == "ack":
                print("✅ Autenticação OK!")
                
                # Envia telemetria de teste
                telemetry = {
                    "type": "telemetry",
                    "payload": {
                        "balance": 10000,
                        "equity": 10000,
                        "floating_pnl": 0,
                        "status": "TEST",
                        "open_positions": []
                    }
                }
                await ws.send(json.dumps(telemetry))
                print("📤 Telemetria enviada")
                
                # Aguarda ACK
                ack = await asyncio.wait_for(ws.recv(), timeout=5)
                print(f"📥 ACK: {json.loads(ack)}")
            else:
                print(f"❌ Auth falhou: {data}")
                
    except Exception as e:
        print(f"❌ Erro: {e}")

if __name__ == '__main__':
    asyncio.run(test())
