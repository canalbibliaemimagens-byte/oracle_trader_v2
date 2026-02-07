# 🌉 Padrão de Arquitetura: Connector Bridge

**Data:** 2026-02-06
**Contexto:** Decisão de usar bibliotecas com diferentes paradigmas de concorrência (Twisted, Blocking I/O, AsyncIO) sob uma interface unificada.

---

## 1. O Problema
O Oracle Trader v2 é construído sobre `asyncio` (Python moderno). No entanto, para conectar com diferentes mercados, precisamos usar SDKs oficiais que nem sempre seguem esse padrão:

1.  **cTrader:** O SDK oficial (`ctrader-open-api`) usa **Twisted** (Deferreds), um framework assíncrono antigo mas robusto para TCP persistente.
2.  **MetaTrader 5:** O SDK oficial (`MetaTrader5`) é **Síncrono/Bloqueante** (chama DLLs do Windows).
3.  **Crypto (CCXT):** O padrão de mercado (`ccxt`) oferece suporte nativo a `asyncio`, mas possui sua própria gestão de loops.

Se o `Executor` (coração do robô) tivesse que lidar com essas diferenças, o código seria inmanutenível.

---

## 2. A Solução: Connector Bridge
Usamos o padrão de projeto **Adapter (ou Bridge)** para isolar a complexidade da implementação "suja" dentro de cada conector, expondo apenas a interface limpa `BaseConnector` para o sistema.

```mermaid
graph TD
    System[Executor (AsyncIO)] -->|await open_order| Interface[BaseConnector ABC]
    
    Interface -->|Implementa| CT[CTraderConnector]
    Interface -->|Implementa| MT[MT5Connector]
    Interface -->|Implementa| CC[CCXTConnector]
    
    subgraph "Bridge Twisted (Legacy Async)"
        CT -->|Twisted Reactor| LibCT[ctrader-open-api]
    end
    
    subgraph "Wrapper Thread (Blocking)"
        MT -->|to_thread| LibMT[MetaTrader5 DLL]
    end
    
    subgraph "Nativo (Modern Async)"
        CC -->|await| LibCC[ccxt.async_support]
    end
```

---

## 3. Implementação por Tecnologia

### 3.1 Caso cTrader (Twisted)
- **Desafio:** Twisted tem seu próprio Event Loop (`reactor`).
- **Solução:** Usamos `asyncioreactor` para rodar o Twisted *dentro* do loop do `asyncio`, ou envelopamos os `Deferreds` em `asyncio.Future`.
- **Resultado:** O Executor chama `await connector.connect()` e não sabe que existe Twisted rodando embaixo.

### 3.2 Caso MetaTrader 5 (Bloomberg/Sync)
- **Desafio:** As funções `mt5.order_send()` travam a thread principal. Se o robô travar esperando a corretora, ele perde ticks.
- **Solução:** Usamos `asyncio.to_thread()` para jogar a chamada bloqueante para uma thread separada.
- **Exemplo:**
  ```python
  # Dentro de connector/mt5/client.py
  async def open_order(self, ...):
      # O Executor continua livre enquanto essa thread roda
      result = await asyncio.to_thread(mt5.order_send, request)
      return self._parse_result(result)
  ```

### 3.3 Caso CCXT (Crypto/Async Nativo)
- **Desafio:** Menor desafio, pois já suporta `async`.
- **Solução:** Apenas mapear os métodos. O `ccxt` já retorna *awaitables*.
- **Exemplo:**
  ```python
  # Dentro de connector/crypto/client.py
  async def open_order(self, ...):
      # Compatibilidade nativa
      return await self.exchange.create_order(...)
  ```

---

## 4. Conclusão
Independente da "sujeira" necessária para falar com a corretora (DLLs antigas, protocolos TCP legados, conexões instáveis), o `Executor` sempre verá:

```python
# Interface Limpa e Previsível
await connector.connect()
await connector.subscribe(symbol)
await connector.open_order(...)
```

Isso garante que podemos plugar **qualquer** mercado (B3 via MT5, Forex via cTrader, Crypto via Binance) sem alterar uma única linha da lógica de trading (`Executor/Preditor`).
