# Guia de Deploy - Oracle Trader v2 (Linux VM)

## 1. Conexão SSH
Acesse a VM usando sua chave SSH:
```bash
ssh -i ~/.ssh/oracle_new ubuntu@163.176.175.219
# ou
ssh -i ~/.ssh/oracle_new ubuntu@163.176.208.248
```

## 2. Preparação do Ambiente
Garanta que o Python 3.10+ e pip estão instalados:
```bash
sudo apt update
sudo apt install -y python3-pip python3-venv git
```

## 3. Clone e Instalação
Clone o projeto na raiz ou diretório desejado:
```bash
# Clone
git clone https://github.com/canalbibliaemimagens-byte/oracle_trader_v2.git
cd oracle_trader_v2

# Criar Virtualenv
python3 -m venv venv
source venv/bin/activate

# Instalar Dependências (Evitando CUDA/GPU na VM)
pip install --upgrade pip

# 1. Instalar PyTorch CPU-only (Leve, sem drivers NVIDIA ~2GB)
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu

# 2. Instalar demais dependências
pip install -r requirements.txt
# O requirements.txt já contém "-e ." que instala o projeto em modo editável

# 3. Baixar Modelos (Obrigatório para rodar)
# O script detecta automaticamente os modelos disponíveis no bucket 'oracle_models'
python scripts/download_model.py

```

## 4. Configuração (Variáveis de Ambiente)
Crie o arquivo `.env` com suas credenciais. Você pode copiar o exemplo ou criar do zero:
```bash
nano .env
```
Cole o conteúdo (ajuste os valores):
```env
# cTrader Credentials
CTRADER_CLIENT_ID=seu_client_id
CTRADER_CLIENT_SECRET=seu_client_secret
CTRADER_ACCESS_TOKEN=seu_access_token
CTRADER_ACCOUNT_ID=seu_account_id

# Supabase (Opcional se persistence desabilitado)
SUPABASE_URL=sua_url
SUPABASE_KEY=sua_key

# Hub
OTS_HUB_URL=ws://163.176.175.219:8000/ws/bot-v2
OTS_HUB_TOKEN=OTS_HUB_TOKEN_0702226
```

## 5. Teste de Conexão (Raw Protocol)
Antes de rodar o bot principal, teste a conexão com o script explorador:
```bash
python scripts/ctrader_explorer.py
```
*Deve conectar, autenticar e baixar símbolos.*

## 6. Execução do Oracle Trader
Para rodar o orchestrator (modo Demo ou Live conforme config):
```bash
# Rodar em primeiro plano (para teste)
python -m orchestrator

# Rodar em background (com nohup)
nohup python -m orchestrator > oracle.log 2>&1 &
tail -f oracle.log
```

### Configuração de Broker
Para alternar entre **Mock** e **cTrader**, edite `config/default.yaml`:
```yaml
broker:
  type: "ctrader"  # ou "mock"
  environment: "demo" # ou "live"
```

## Troubleshooting
- **Erro de Import:** Certifique-se de que rodou `pip install -r requirements.txt` (que executa `pip install -e .`).
- **Permissão Negada:** Verifique permissões de escrita em `logs/` e `data/`.
