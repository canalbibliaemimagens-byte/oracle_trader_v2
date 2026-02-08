# Nota: Bug NoTransition no cTrader Open API

**Data:** 2026-02-07
**Contexto:** Script `ctrader_explorer.py` falhando com erro de state machine.

## Problema

```
automat._core.NoTransition: no transition for MethodicalInput(method=<function _ClientMachine._clientDisconnected>)
in MethodicalState(method=<function _ClientMachine._connecting>)
```

O erro ocorre na biblioteca `ctrader-open-api` durante tentativa de conexão.

## Causa Provável

Incompatibilidade entre versões:
- `automat` (state machine library)
- `ctrader-open-api` 
- `Twisted`

O callback `_clientDisconnected` está sendo chamado enquanto ainda no estado `_connecting`, o que não é permitido pela máquina de estados.

## Workarounds

### 1. Downgrade automat
```bash
pip install automat==20.2.0
```

### 2. Usar JSON API em vez de Protobuf
A cTrader Open API também suporta JSON (mais simples):
```
wss://demo.ctraderapi.com:5036/socket.io/?transport=websocket
```

### 3. Verificar se o servidor está acessível
O mercado de crypto (BTCUSD) está aberto mas pode haver problemas de firewall/proxy.

## Solução Temporária

O sistema principal (`orchestrator/cli.py`) usa o mesmo código e deve funcionar normalmente pois:
1. Inicializa o asyncioreactor no `lifecycle.py` no momento correto
2. Roda dentro do event loop principal

O script standalone tem dificuldade em replicar essa ordem de inicialização.

## Próximos Passos

1. Testar com o orchestrator completo (`python -m orchestrator`)
2. Se falhar, downgrade do automat
3. Última opção: usar JSON WebSocket API
