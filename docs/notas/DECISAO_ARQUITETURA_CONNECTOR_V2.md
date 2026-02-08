# Decisão Arquitetural: Refatoração do Connector cTrader (Raw Protocol)

**Data:** 2026-02-07
**Status:** APROVADO PARA IMPLEMENTAÇÃO

## Contexto
O atual connector (`CTraderConnector`) depende da biblioteca `ctrader-open-api`, que carrega uma dependência legada e conflitante da biblioteca `automat` (state machine). Isso causou:
1.  Bugs críticos (`NoTransition`) no Windows/Linux ao conectar.
2.  Necessidade de travar versões antigas do `Twisted` (`21.7.0`), impedindo atualizações de segurança e performance.
3.  Fragilidade no tratamento de erros de rede.

## Decisão
**Substituir a dependência da classe `Client` da biblioteca oficial por uma implementação "Raw" baseada em Twisted Protocol + Protobuf manuais.**

Confirmamos através do script `scripts/ctrader_deep_dive.py` que é possível:
1.  Conectar via SSL usando Twisted puro (sem erros de state machine).
2.  Construir e parsear mensagens Protobuf usando os módulos `_pb2.py` gerados pela library (sem usar a lógica de cliente dela).
3.  Receber streams de preço (Spots) em tempo real e executar trades.

## Benefícios
1.  **Resolução de Conflitos:** Permite remover o `Twisted==21.7.0` e usar a versão mais recente, compatível com o resto do ecossistema Python moderno.
2.  **Performance:** Elimina a sobrecarga da máquina de estados complexa da `automat`.
3.  **Controle:** Permite implementar lógica de reconexão e heartbeat customizada e robusta.
4.  **Extensibilidade:** Acesso direto a todos os eventos (como `ProtoOASpotEvent`) sem depender de callbacks limitados da library.

## Plano de Implementação
1.  Criar `connector/ctrader/raw_client.py` implementando a lógica validada no script deep dive.
2.  Atualizar `requirements.txt` removendo travas de versão do Twisted.
3.  Atualizar `CTraderConnector` para usar o novo `raw_client`.
