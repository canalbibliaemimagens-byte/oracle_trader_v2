# 🔍 AUDITORIA: Oracle Trader v2.0

**Data:** 2026-02-07  
**Escopo:** Confronto código vs documentação, bugs, inconsistências e limpeza de lixo

---

## 🔴 BUGS CRÍTICOS

### BUG-1: `VirtualPosition.size` retorna `0.0` — FEATURE RL QUEBRADA

**Arquivo:** `core/models.py` linha 130  
**Impacto:** CRÍTICO — invalida o modelo PPO em produção

O `VirtualPosition` no `core/models.py` tem um property `size` que retorna `0.0` hardcoded:

```python
@property
def size(self) -> float:
    return 0.0  # Placeholder
```

Porém, `FeatureCalculator.calc_rl_features()` usa `position.size * 10` como feature RL:

```python
pos_features = [
    float(position.direction),
    float(position.size) * 10,         # ← SEMPRE 0.0 !!
    np.tanh(float(position.current_pnl) / 100.0)
]
```

O `VirtualPositionManager` no `preditor/virtual_position.py` converte para `VirtualPosition` do core via `as_core_virtual_position()`, mas esse método não copia `lot_sizes` — e mesmo que copiasse, o `VirtualPosition.size` não teria como calcular (é um frozen-like DTO).

**Solução:** Mudar `as_core_virtual_position()` para injetar o `size` correto:

```python
def as_core_virtual_position(self):
    from ..core.models import VirtualPosition
    vp = VirtualPosition(
        direction=self.direction,
        intensity=self.intensity,
        entry_price=self.entry_price,
        current_pnl=self.current_pnl,
    )
    # Override size com valor calculado
    vp._size_override = self.size  # lot_sizes[intensity]
    return vp
```

Ou simplesmente remover o `VirtualPosition` do core (é redundante) e usar `VirtualPositionManager` diretamente no `FeatureCalculator`.

---

### BUG-2: Imports absolutos no Connector — Quebra como pacote

**Arquivos afetados:**
- `connector/base.py:17` → `from core.models import ...`
- `connector/ctrader/client.py:22` → `from core.models import ...`
- `connector/ctrader/client.py:23` → `from connector.base import ...`
- `connector/ctrader/client.py:26` → `from connector.rate_limiter import ...`
- `connector/ctrader/bar_detector.py:18-19` → `from core.constants import ...`, `from core.models import ...`

Todos os outros módulos usam imports relativos (`from ..core.models`), mas o connector usa **imports absolutos** (`from core.models`). Isso funciona se rodar de dentro do diretório raiz, mas **quebra quando instalado como pacote** ou executado via `python -m oracle_trader_v2`.

**Solução:** Trocar para imports relativos:

```python
# connector/base.py
from ..core.models import AccountInfo, Bar, OrderResult, Position

# connector/ctrader/client.py
from ...core.models import AccountInfo, Bar, ...
from ..base import BaseConnector
from ..rate_limiter import RateLimiter
```

---

### BUG-3: Config YAML — `persistence.enabled` nunca é lido corretamente

**Arquivo:** `config/default.yaml` + `orchestrator/orchestrator.py`

No YAML, a config de persistence está aninhada:
```yaml
persistence:
  enabled: false       # ← aninhado
supabase_url: "..."    # ← nível raiz (inconsistente!)
supabase_key: "..."    # ← nível raiz
```

Mas o Orchestrator lê:
```python
self.config.get("persistence_enabled", True)  # ← chave errada!
self.config.get("supabase_url", "")            # ← OK (nível raiz)
```

O `persistence.enabled` do YAML vira `config["persistence"]["enabled"]`, mas o código busca `config["persistence_enabled"]` — chave que não existe. Resultado: **persistence sempre ativo** (default `True`).

**Solução:** Alinhar config:
```python
enabled=self.config.get("persistence", {}).get("enabled", True),
```

E mover `supabase_url`/`supabase_key` para dentro de `persistence:` no YAML.

---

### BUG-4: `Decision.OPEN` removida mas spec a define

**Arquivo:** `executor/sync_logic.py` vs `docs/modules/SPEC_EXECUTOR.md`

A spec define 4 decisões: `NOOP`, `OPEN`, `CLOSE`, `WAIT_SYNC`  
O código implementa apenas 3: `NOOP`, `CLOSE`, `WAIT_SYNC`

`OPEN` foi removida e a abertura é delegada ao `SyncState.update()` que retorna `bool`. Isso **funciona**, mas diverge da spec e torna o fluxo menos claro. A spec deve ser atualizada para refletir a implementação atual, ou o código deve adicionar `Decision.OPEN`.

---

## 🟡 INCONSISTÊNCIAS (Código vs Documentação)

### INC-1: Estrutura de diretórios divergente

**Documentação diz `oracle_v2/`**, código real é **`oracle_trader_v2/`**

O README, PROJECT_STRUCTURE e todas as specs referem ao pacote como `oracle_v2/`. O nome real do diretório/pacote é `oracle_trader_v2/`. Comandos de execução no README (`python -m oracle_v2.main`) não funcionam.

### INC-2: `connector/ctrader/symbols.py` — previsto na spec, não existe

`SPEC_CONNECTOR.md` lista `symbols.py` na estrutura. O arquivo não existe. A funcionalidade de mapeamento `symbol_id` está inline no `client.py`.

### INC-3: `connector/ctrader/messages.py` — existe no código, ausente da spec

O arquivo `messages.py` (368 linhas, wrappers protobuf) existe no código mas não é listado na spec do Connector.

### INC-4: Arquivos extras não documentados

| Arquivo | Existe | Na Spec |
|---------|--------|---------|
| `connector/hub_client.py` | ✅ | ❌ |
| `connector/rate_limiter.py` | ✅ | ❌ |
| `connector/errors.py` | ✅ | ❌ |
| `connector/ctrader/protocol.py` | ✅ | ❌ |
| `connector/ctrader/raw_client.py` | ✅ | ❌ |
| `connector/ctrader/messages.py` | ✅ | ❌ |
| `executor/price_converter.py` | ✅ | Mencionado mas não na estrutura |

### INC-5: README diz `models/` tem ZIPs, pasta está vazia

`models/` só tem `.gitkeep`. O README mostra `EURUSD_M15.zip`, `GBPUSD_M15.zip`, etc.

### INC-6: `notebooks/` vazio — spec prevê `training/` com notebook e utils

A spec PROJECT_STRUCTURE define:
```
training/
├── oracle-v8.ipynb
├── requirements.txt
└── utils/
    ├── data_loader.py
    └── zip_builder.py
```
No código: `notebooks/` está **completamente vazio**.

### INC-7: Arquivos de config faltantes vs spec

| Spec prevê | Existe |
|------------|--------|
| `config/default.yaml` | ✅ |
| `config/executor_symbols.json` | ✅ |
| `config/dev.yaml` | ❌ |
| `config/credentials.env.example` | ❌ |
| `.env.example` | ❌ |
| `Dockerfile` | ❌ |
| `docker-compose.yml` | ❌ |
| `main.py` (entry point) | ❌ (usa `__main__.py`) |

### INC-8: Spec define `open_order(sl, tp)` como USD, docstring da base diz USD, mas Executor converte para preço

O `BaseConnector.open_order()` documenta SL/TP como "em USD", mas o `Executor` faz a conversão para preço absoluto ANTES de chamar o connector. Então na prática, o connector recebe **preço absoluto**. A docstring do `base.py` deveria dizer "preço absoluto".

### INC-9: Token/URL hardcoded no YAML e scripts

`config/default.yaml` contém URL e token do Hub hardcoded:
```yaml
hub:
  url: "ws://163.176.175.219:8000/ws/bot-v2"
  token: "OTS_HUB_TOKEN_0702226"
```
Scripts `test_hub_connection.py` e `test_mock_orchestrator.py` também têm credenciais hardcoded.

---

## 🗑️ LIXO A REMOVER

### Arquivos que devem ser removidos

| Arquivo/Dir | Motivo |
|-------------|--------|
| `__pycache__/` (todos os 12 dirs) | Cache Python — não versionar |
| `.pytest_cache/` | Cache pytest |
| `data_EURUSD_M15.csv` (131KB) | Dados de teste que não são referenciados por nenhum código |
| `test_results.txt` (1013 linhas, 58KB) | Output de teste antigo — não versionar |
| `accounts_found.txt` | Output de script, contém IDs de conta reais — **risco de segurança** |
| `specs_EURUSD.json` | Artefato de script `get_symbol_specs.py`, não referenciado |
| `specs_EURUSD.txt` | Idem |
| `specs_USDJPY.json` | Idem |
| `specs_USDJPY.txt` | Idem |
| `specs_table.txt` | Arquivo vazio (0 bytes) |
| `notebooks/` | Diretório vazio sem nem `.gitkeep` |
| `scripts/inspect_deals.py` | 3 linhas, script descartável de debug |
| `scripts/inspect_proto.py` | Script descartável de exploração protobuf |
| `scripts/check_ml.py` | Verifica imports — descartável |
| `scripts/check_proto.py` | Verifica protobuf — descartável |
| `scripts/diagnose_network.py` | Diagnóstico pontual de rede — descartável |
| `scripts/test_hub_connection.py` | Teste manual com credenciais hardcoded |
| `scripts/test_mock_orchestrator.py` | Teste manual com credenciais hardcoded |
| `scripts/verify_refactor.py` | Verificação pontual pós-refactor |
| `docs/backup/` | Versões antigas de specs (3 arquivos) |
| `docs/notas/BUG_NOTRANSITION_TWISTED.md` | Bug já resolvido (migrou para raw client) |

### Arquivos questionáveis (avaliar)

| Arquivo | Motivo para manter | Motivo para remover |
|---------|-------------------|---------------------|
| `CHANGELOG_CORRECOES.md` | Histórico | Pode ir pro Git history |
| `docs/ORACLE_V8_INCONSISTENCIAS.md` | Roadmap do notebook | Itens antigos, muitos não se aplicam mais |
| `docs/Conexão VMs.txt` | Notas de infra | Pode ir para docs/notas/ ou wiki |
| `scripts/ctrader_explorer_raw.py` | Debug útil em produção | Duplica funcionalidade de `ctrader_explorer.py` |
| `scripts/ctrader_deep_dive.py` | Debug avançado | Específico demais |

---

## 🔧 PROBLEMAS MENORES

### PM-1: `VirtualPosition` duplicado
`core/models.py` define `VirtualPosition` como DTO.  
`preditor/virtual_position.py` define `VirtualPositionManager` com toda a lógica.  
O DTO do core é quase inútil — existe só para o `FeatureCalculator`, mas com o `size` quebrado.

### PM-2: `TickData` e `OrderUpdate` não usados
`core/models.py` define `TickData` e `OrderUpdate` que não são importados/usados por nenhum módulo do sistema (apenas no `client.py` do ctrader).

### PM-3: `requirements.txt` tem `==` truncado
```
pytest-asyncio>=1.3.0
```
Última linha sem newline — pode causar problemas em alguns pip.

### PM-4: `pydantic` nas dependências mas não usado
`pyproject.toml` e `requirements.txt` listam `pydantic>=2.0.0`, mas nenhum arquivo do projeto importa pydantic.

### PM-5: Spread conversion no Orchestrator pode estar errada
```python
# orchestrator.py ~linha 300
spread_pips = info["spread_points"] * point * 10000
if "JPY" in symbol:
    spread_pips = info["spread_points"] * point * 100
```
Se `spread_points` já é em points (ex: 7 para EURUSD), a fórmula `7 * 0.00001 * 10000 = 0.7 pips` está correta. Mas se o broker retorna spread como inteiro de points (70), a conversão dá errado. Necessita validação com dados reais.

### PM-6: `__main__.py` usa import absoluto
```python
from oracle_trader_v2.orchestrator.cli import main
```
Deveria ser relativo para consistência:
```python
from .orchestrator.cli import main
```

---

## 📋 RESUMO EXECUTIVO

| Categoria | Qtd |
|-----------|-----|
| 🔴 Bugs Críticos | 4 |
| 🟡 Inconsistências Doc vs Código | 9 |
| 🗑️ Arquivos Lixo (remover) | ~30 |
| 🔧 Problemas Menores | 6 |

**Prioridade imediata:** BUG-1 (feature size=0.0) e BUG-2 (imports absolutos) — sem esses fixes, o sistema não funciona corretamente como pacote e o modelo PPO recebe features incorretas.
