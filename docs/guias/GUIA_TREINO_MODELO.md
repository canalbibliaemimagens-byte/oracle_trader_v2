# Guia de Treinamento do Modelo (Kaggle/Colab)

Este guia descreve passo-a-passo como utilizar o notebook `notebooks/oracle_v2_training_pipeline.ipynb` para treinar, validar e implantar novos modelos para o Oracle Trader v2.

**Pré-requisitos:**
*   Conta no **Kaggle** (Recomendado) ou Google Colab.
*   Credenciais da API cTrader (Client ID, Secret, Token).
*   Credenciais do Supabase (URL, Key).

---

## 1. Visão Geral do Pipeline

O notebook automatiza todo o processo de Reinforcement Learning (HMM + PPO):
1.  **Download:** Baixa dados históricos direto da cTrader API.
2.  **HMM:** Treina modelo Hidden Markov Model para detectar regimes de mercado.
3.  **PPO:** Treina agente de Deep RL (Stable-Baselines3) usando GPU.
4.  **Backtest:** Valida o modelo em dados recentes (Out-of-Sample).
5.  **Export:** Gera um ZIP v2.0 com metadados e faz upload para o Supabase.

---

## 2. Configuração do Ambiente (Kaggle)

Recomendamos usar o Kaggle pela facilidade de uso das GPUs T4 x2 gratuitas.

### 2.1 Importar Notebook
1.  Crie um novo Notebook no Kaggle.
2.  File -> Import Notebook -> Upload `oracle_v2_training_pipeline.ipynb`.

### 2.2 Configurar Secrets (Segurança)
Não cole suas chaves no código! Use a funcionalidade "Secrets" do Kaggle (Add-ons -> Secrets).

Adicione as seguintes chaves:
*   `CTRADER_CLIENT_ID`
*   `CTRADER_CLIENT_SECRET`
*   `CTRADER_ACCESS_TOKEN`
*   `CTRADER_ACCOUNT_ID`
*   `SUPABASE_URL`
*   `SUPABASE_KEY`

### 2.3 Aceleração
1.  No painel direito, em "Session options", selecione **Accelerator: GPU T4 x2**.
2.  Internet: **On**.

---

## 3. Executando o Treino

### 3.1 Configuração (Seção 0)
No topo do notebook, ajuste os parâmetros da "Seção 0":

```python
SYMBOL = "EURUSD"              # Ativo
TIMEFRAME = "M15"              # Timeframe
HISTORY_AMOUNT = 2             # Quantidade
HISTORY_UNIT = "years"         # Unidade (years/months/days)
```

### 3.2 Execução Automática ("Run All")
O notebook foi desenhado para rodar sem intervenção humana.
1.  Clique em **Runtime -> Run All** (ou "Save Version -> Save & Run All").
2.  O processo levará entre 30 a 60 minutos (para 2 anos de dados M15).

---

## 4. O Resultado (ZIP v2.0)

Ao final, o notebook gera um arquivo `SYMBOL_M15.zip` (ex: `EURUSD_M15.zip`) contendo:
1.  `_hmm.pkl`: Modelo de regimes.
2.  `_ppo.zip`: Modelo neural (pesos).
3.  **Metadados:** Gravados no comentário do ZIP (`zip.comment`), contendo config, métricas e hash de integridade.

O arquivo é enviado automaticamente para o **Supabase Storage** (`oracle_models/`).

---

## 5. Como Usar o Modelo no Bot

1.  Baixe o arquivo ZIP do Supabase (ou da saída do Kaggle).
2.  Coloque na pasta `models/` do projeto local:
    ```bash
    c:/oracle_trader_v2/models/EURUSD_M15.zip
    ```
3.  O `ModelLoader` do bot detectará automaticamente o formato v2.0 e carregará as configurações embutidas no arquivo.

> **Nota:** Você não precisa mais configurar `normalization_stats.json` ou `hparams.json` manualmente. Tudo está dentro do ZIP.
