# Solução para Conexão cTrader (Bypass Automat/Twisted)

**Data:** 2026-02-07
**Status:** ✅ RESOLVIDO

## Problema
A biblioteca oficial `ctrader-open-api` utiliza uma máquina de estados (`automat`) antiga que conflita com versões recentes do `Twisted`, causando o erro `NoTransition` no Windows/Linux ao tentar conectar.

## Solução Definitiva: Raw Twisted + Protobuf Manual

Em vez de tentar corrigir a biblioteca (downgrades falharam), criamos uma implementação "Raw" que:
1.  Usa `Twisted` puro para gerenciamento TCP/SSL (que funciona perfeitamente).
2.  Usa os arquivos gerados `_pb2.py` da biblioteca apenas para **definição** das mensagens.
3.  Faz o envelope (`ProtoMessage`) e serialização manualmente.

### Script de Referência
`scripts/ctrader_explorer_raw.py`

### Detalhes Técnicos Importantes
1.  **ProtoMessage Location**: `ProtoMessage` (o envelope principal) está em `ctrader_open_api.messages.OpenApiCommonMessages_pb2`, **NÃO** em `OpenApiMessages_pb2` nem `OpenApiModelMessages_pb2`.
2.  **PayloadTypes**: Os enums de tipo (ex: `PROTO_OA_ACCOUNT_AUTH_REQ`) estão em `OpenApiModelMessages_pb2`.
3.  **Mensagens de Negócio**: As mensagens (ex: `ProtoOAAccountAuthReq`) estão em `OpenApiMessages_pb2`.

### Como Implementar no Projeto Principal
Se o `CTraderConnector` (que usa a lib quebrada via bridge) também falhar no ambiente de produção, devemos refatorá-lo para seguir o padrão do `ctrader_explorer_raw.py`:
- Remover a dependência da classe `Client` da lib.
- Manter apenas a dependência dos `messages`.
- Implementar um `Protocol` Twisted simples.

Isso garante estabilidade total e remove a dependência da máquina de estados frágil.
