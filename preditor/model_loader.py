"""
Oracle Trader v2.0 - Model Loader
==================================

Carrega modelos do formato ZIP v2.0:
  {symbol}_{timeframe}.zip
    ├── {symbol}_{timeframe}_hmm.pkl
    └── {symbol}_{timeframe}_ppo.zip

Metadata fica no zip.comment (JSON).
"""

import json
import logging
import pickle
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("Preditor.ModelLoader")


@dataclass
class ModelBundle:
    """Pacote completo de um modelo carregado."""
    symbol: str
    timeframe: str
    hmm_model: Any              # hmmlearn.GaussianHMM
    ppo_model: Any              # stable_baselines3.PPO
    metadata: dict
    training_config: dict
    hmm_config: dict
    rl_config: dict


class ModelLoader:
    """Carrega modelos do formato ZIP v2.0."""

    SUPPORTED_VERSIONS = ["2.0"]

    REQUIRED_METADATA_KEYS = [
        "format_version",
        "symbol",
        "training_config",
        "hmm_config",
        "rl_config",
        "actions",
    ]

    @staticmethod
    def load(zip_path: str) -> Optional[ModelBundle]:
        """
        Carrega modelo completo do ZIP.

        Args:
            zip_path: Caminho para o arquivo ZIP.

        Returns:
            ModelBundle se sucesso, None se falhar.
        """
        path = Path(zip_path)
        if not path.exists():
            logger.error(f"Arquivo não encontrado: {zip_path}")
            return None

        try:
            with zipfile.ZipFile(path, 'r') as zf:
                # 1. Extrai metadata do zip.comment
                if not zf.comment:
                    logger.error(f"ZIP sem metadata (comment vazio): {zip_path}")
                    return None

                metadata = json.loads(zf.comment.decode('utf-8'))

                # 2. Valida metadata
                if not ModelLoader.validate_metadata(metadata):
                    logger.error(f"Metadata inválido em {zip_path}")
                    return None

                # 3. Valida versão
                version = metadata.get("format_version", "1.0")
                if version not in ModelLoader.SUPPORTED_VERSIONS:
                    logger.error(f"Versão não suportada: {version} (suportadas: {ModelLoader.SUPPORTED_VERSIONS})")
                    return None

                # 4. Extrai info do símbolo
                symbol_info = metadata["symbol"]
                symbol = symbol_info["name"]
                timeframe = symbol_info["timeframe"]
                prefix = f"{symbol}_{timeframe}"

                hmm_file = f"{prefix}_hmm.pkl"
                ppo_file = f"{prefix}_ppo.zip"

                # 5. Verifica que ambos os arquivos existem no ZIP
                zip_contents = zf.namelist()
                if hmm_file not in zip_contents:
                    logger.error(f"Arquivo HMM não encontrado no ZIP: {hmm_file}")
                    return None
                if ppo_file not in zip_contents:
                    logger.error(f"Arquivo PPO não encontrado no ZIP: {ppo_file}")
                    return None

                # 6. Carrega HMM
                with zf.open(hmm_file) as f:
                    hmm_data = pickle.load(f)
                    if isinstance(hmm_data, dict):
                        hmm_model = hmm_data.get('model', hmm_data)
                    else:
                        hmm_model = hmm_data

                # 7. Carrega PPO (extrai para temp porque SB3 precisa de path)
                from stable_baselines3 import PPO

                with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as tmp:
                    tmp.write(zf.read(ppo_file))
                    tmp_path = tmp.name

                ppo_model = PPO.load(tmp_path, device='cpu')
                Path(tmp_path).unlink()  # Limpa temp

                logger.info(f"Modelo carregado: {symbol} ({timeframe}) v{version}")

                return ModelBundle(
                    symbol=symbol,
                    timeframe=timeframe,
                    hmm_model=hmm_model,
                    ppo_model=ppo_model,
                    metadata=metadata,
                    training_config=metadata.get("training_config", {}),
                    hmm_config=metadata.get("hmm_config", {}),
                    rl_config=metadata.get("rl_config", {}),
                )

        except json.JSONDecodeError as e:
            logger.error(f"Erro ao parsear metadata JSON: {e}")
            return None
        except ImportError:
            logger.error("stable_baselines3 não instalado. Instale com: pip install stable-baselines3")
            return None
        except Exception as e:
            logger.error(f"Erro ao carregar modelo {zip_path}: {e}")
            return None

    @staticmethod
    def load_metadata_only(zip_path: str) -> Optional[dict]:
        """
        Carrega apenas o metadata do ZIP (sem carregar modelos ML).
        Útil para validação rápida e listagem.

        Returns:
            Dict com metadata ou None se falhar.
        """
        path = Path(zip_path)
        if not path.exists():
            return None

        try:
            with zipfile.ZipFile(path, 'r') as zf:
                if not zf.comment:
                    return None
                return json.loads(zf.comment.decode('utf-8'))
        except Exception:
            return None

    @staticmethod
    def validate_metadata(metadata: dict) -> bool:
        """Valida se metadata tem todos os campos obrigatórios."""
        for key in ModelLoader.REQUIRED_METADATA_KEYS:
            if key not in metadata:
                logger.warning(f"Metadata: campo obrigatório ausente: '{key}'")
                return False
        return True
