# Registro de Correções: Configuração cTrader e Pipeline

Este documento detalha os problemas críticos encontrados e resolvidos durante a configuração do pipeline de dados e treinamento do **Oracle Trader v2**, especificamente para a integração com a **cTrader Open API**.

## 1. Identificação da Conta (Account ID vs Login ID)
**Problema:** A API retornava `INVALID_ACCOUNT_ID` ou desconectava silenciosamente.
**Causa:** Confusão entre o *Login ID* (número na tela do cTrader, ex: 5150xxx) e o *Trading Account ID* (ID interno da API).
**Solução:**
- O `CTRADER_ACCOUNT_ID` no `.env` deve ser o ID da conta de negociação (CTID), não o login.
- Contas **Demo** e **Live** têm IDs completamente diferentes.
- **Script de Diagnóstico:** `scripts/list_ctrader_accounts.py` foi criado para listar todas as contas vinculadas ao token e mostrar o ID correto.

## 2. Cálculo de Tamanho de Lote (Lot Size)
**Problema:** O notebook calculava `min_lot` incorretamente (ex: 1000.0 ou 100.0), impedindo a execução correta da lógica de trading no ambiente RL.
**Diagnóstico:** A API retorna volumes em "Unidades Brutas" (Raw Units) escaladas, não em Lotes padrão Forex.
**Correção Crítica:**
- A fórmula correta para converter o volume bruto da API para Lotes é dividir pelo valor do campo `lotSize` fornecido pela API.
- **Fórmula Universal:** `Lot = RawVolume / lotSize`
- No Forex (maioria dos pares): `lotSize` é **10.000.000**.
  - Exemplo: `Raw 100,000` (minVolume) / `10,000,000` = **0.01 Lot**.
- O código anterior dividia por valores fixos incorretos, gerando erros. O script `get_symbol_specs.py` foi atualizado para usar essa leitura dinâmica.

## 3. Dependências e Protocolo (Python)
**Problema:** Erros de conexão SSL, timeouts e falhas na serialização Protobuf.
**Solução:**
- **Twisted:** Deve ser fixado na versão `21.7.0`. Versões novas quebram o loop de eventos da `ctrader-open-api`.
- **Protobuf:** Fixado em `3.20.1` para compatibilidade com os stubs gerados.
- **Uso do Protobuf:** A função `Protobuf.extract()` **NÃO** deve ser usada ao *enviar* mensagens (`client.send()`), apenas ao *receber*.
    - **Incorreto:** `client.send(Protobuf.extract(msg))`
    - **Correto:** `client.send(msg)`

## 4. Valor do Ponto (Point Value) no Notebook
**Problema:** O notebook de treino assume custos e valores fixos que podem distorcer o treinamento em pares não-USD.
**Cenário Atual:**
- O notebook define `PIP_VALUE_PER_LOT = 10.0` (padrão USD).
- Define `COMMISSION_PER_LOT = 7.0`.
**Impacto:**
- Para **EURUSD**: O cálculo é exato.
- Para **USDJPY, XAUUSD, indices**: O cálculo é uma **aproximação**.
    - O modelo aprende a maximizar uma "pontuação" baseada em pips, não o valor financeiro exato em Dólares.
- **Risco:** Em pares onde o valor do pip é menor (ex: USDJPY ≈ $6.60), o modelo pode subestimar o custo relativo da comissão se usar o valor fixo de $10.00.
**Recomendação:**
- Para pares exóticos ou cruzes, considere ajustar manualmente `PIP_VALUE_PER_LOT` na **Seção 1 (Parâmetros Avançados)** do notebook se desejar precisão financeira absoluta.
- Para fins de RL (aprender a operar), a "pontuação fixa" geralmente funciona bem, desde que o Sharpe Ratio seja o guia principal.
