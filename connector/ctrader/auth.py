"""
Oracle Trader v2.0 - cTrader OAuth2 Authentication
====================================================

Gerencia tokens OAuth2 para a cTrader Open API.
Usa a lib ctrader-open-api (Auth class) para refresh.

Fluxo:
  1. Na inicialização, usa access_token do .env
  2. Se token expirar, usa refresh_token para renovar
  3. Persiste tokens atualizados em .env (futuro) ou memória
"""

import logging
import time
from typing import Optional

logger = logging.getLogger("Connector.cTrader.Auth")


class OAuth2Manager:
    """Gerencia tokens OAuth2 para cTrader."""

    def __init__(self, credentials: dict):
        """
        Args:
            credentials: Dict com:
                client_id, client_secret, access_token,
                refresh_token (opcional), account_id
        """
        self.client_id: str = credentials['client_id']
        self.client_secret: str = credentials['client_secret']
        self.access_token: str = credentials.get('access_token', '')
        self.refresh_token: str = credentials.get('refresh_token', '')
        self.account_id: str = credentials.get('account_id', '')
        self.expires_at: float = 0  # Unix timestamp

    def get_valid_token(self) -> Optional[str]:
        """
        Retorna token válido. Tenta refresh se expirado.

        Returns:
            Access token string, ou None se não conseguir.
        """
        if self._is_token_valid():
            return self.access_token

        if self.refresh_token:
            success = self._do_refresh()
            if success:
                return self.access_token

        # Se tem token mas não sabe se é válido, retorna mesmo assim
        # (a API vai rejeitar e podemos tratar o erro)
        if self.access_token:
            logger.warning("Token pode estar expirado, tentando usar mesmo assim")
            return self.access_token

        logger.error("Nenhum token disponível")
        return None

    def _is_token_valid(self) -> bool:
        """Token válido se expira em mais de 5 minutos."""
        if self.expires_at == 0:
            return False  # Nunca verificado
        return time.time() < (self.expires_at - 300)

    def _do_refresh(self) -> bool:
        """Renova token usando refresh_token via ctrader-open-api Auth."""
        try:
            from ctrader_open_api import Auth

            auth = Auth(self.client_id, self.client_secret, "")
            result = auth.refreshToken(self.refresh_token)

            if 'access_token' in result:
                self.access_token = result['access_token']
                self.refresh_token = result.get('refresh_token', self.refresh_token)
                expires_in = result.get('expires_in', 2592000)  # Default 30 dias
                self.expires_at = time.time() + expires_in
                logger.info(f"Token renovado, expira em {expires_in}s")
                return True
            else:
                error = result.get('error', 'unknown')
                error_desc = result.get('error_description', '')
                logger.error(f"Falha no refresh: {error} - {error_desc}")
                return False

        except ImportError:
            logger.error("ctrader-open-api não instalado")
            return False
        except Exception as e:
            logger.error(f"Erro no refresh token: {e}")
            return False
