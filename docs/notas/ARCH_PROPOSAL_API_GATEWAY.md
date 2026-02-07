# Proposta de Arquitetura: Universal API Gateway (Signaling Server)

**Data:** 07/02/2026
**Contexto:** Definição da arquitetura do módulo `api/` (atualmente ausente).

## 1. O Conceito Proposto
O usuário propôs desacoplar o módulo `api/` do container do Oracle Trader, transformando-o em um **servidor de sinalização universal e independente**.

### Cenário:
- **N Containers de Execução (Oracle Core):**
    - Container A: Oracle v2 + cTrader Connector (Conta X)
    - Container B: Oracle v2 + MT5 Connector (Conta Y)
- **1 Servidor Central (API Gateway/Hub):**
    - Recebe dados de telemetria/sinais de todos os containers.
    - Serve o Dashboard Unificado.
    - Gerencia comandos externos para os containers.

## 2. Análise Técnica

### ✅ Vantagens (Pros)
1.  **Agnosticismo de Broker Real:** Um único dashboard pode monitorar múltiplas instâncias rodando em brokers diferentes (cTrader, MT5, Binance) simultaneamente.
2.  **Segurança e Isolamento:** O container de trading (que tem as chaves da conta) não precisa expor portas HTTP/WS publicamente. Ele apenas se conecta como *cliente* ao Hub Central (conexão de saída). Isso fura NATs e Firewalls facilmente sem configurar VPNs.
3.  **Escalabilidade:** Podemos subir 10 bots e todos reportam para o mesmo lugar.
4.  **Persistência Desacoplada:** O Hub pode ser responsável por gravar logs unificados no Supabase, tirando essa carga do loop de trading crítico.

### ⚠️ Desafios (Cons)
1.  **Ponto Único de Falha:** Se o servidor API cair, perdemos a visibilidade (embora o trading possa continuar rodando "cego").
2.  **Latência Adicional:** Comandos manuais (ex: "Zerar Posição") agora fazem o caminho: `Admin -> Hub -> Oracle Container`. Em HFT isso seria ruim, mas para o Oracle (M15) é irrelevante.
3.  **Complexidade de Infra:** Exige manter mais um serviço rodando (o Hub).

## 3. Modelo de Tópicos (Channels)

A sugestão de `id+conta+key` se traduz bem para um modelo Pub/Sub (Publish/Subscribe):

**Estrutura de Tópicos Sugerida:**
- `oracle/{instance_id}/telemetry`: Dados de OHLCV, PnL, Posições (Oracle -> Hub).
- `oracle/{instance_id}/signals`: Sinais gerados pelo Preditor (Oracle -> Hub).
- `oracle/{instance_id}/commands`: Comandos de controle (Hub -> Oracle).

**Auth:**
- Cada instância do Oracle recebe um `ORACLE_INSTANCE_TOKEN` para se autenticar no Hub.

## 4. Veredito

**Faz todo sentido.**

A arquitetura atual (API embutida) é "monolítica" no sentido de deployment: cada bot tem sua própria API. Para quem roda múltiplos bots, é um pesadelo ter 5 abas de dashboard abertas.

**Transformar a API em um "Oracle Hub" centralizado é a evolução natural para uma arquitetura de frota (Fleet Architecture).**

### Implementação Recomendada:
1.  **Não criar `api/` dentro do `oracle_v2`** como um servidor.
2.  Criar um novo projeto/repositório (ou pasta `services/hub`) para o **Oracle Hub** (FastAPI + Websockets).
3.  No `oracle_v2`, o módulo `api` vira um **Client** (`api_client.py`) que apenas envia dados para o Hub.

---
**Conclusão:** A proposta é aprovada e recomenda-se seguir nessa direção para a v2.1 ou implementar já par a v2.0 se o escopo permitir.
