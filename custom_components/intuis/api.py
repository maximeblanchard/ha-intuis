"""Client asynchrone pour l'API Muller Intuitiv / Netatmo."""

from __future__ import annotations

import logging
import time
from typing import Any

import aiohttp

from .const import (
    APP_VERSION,
    GET_MEASURE_URL,
    HOMES_DATA_URL,
    HOME_STATUS_URL,
    OAUTH_CLIENT_ID,
    OAUTH_CLIENT_SECRET,
    OAUTH_SCOPE,
    OAUTH_USER_PREFIX,
    TOKEN_URL,
)

_LOGGER = logging.getLogger(__name__)

TIMEOUT = aiohttp.ClientTimeout(total=30)


class IntuisError(Exception):
    """Erreur générique Intuis."""


class IntuisAuthError(IntuisError):
    """Erreur d'authentification."""


class IntuisConnectionError(IntuisError):
    """Erreur de connexion réseau."""


class IntuisApi:
    """Client pour communiquer avec l'API Muller Intuitiv / Netatmo."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        username: str,
        password: str,
    ) -> None:
        self._session = session
        self._username = username
        self._password = password
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._token_expires_at: float = 0.0

    @property
    def is_authenticated(self) -> bool:
        """Indique si un jeton actif est présent."""
        return self._access_token is not None and time.time() < self._token_expires_at

    async def async_login(self) -> None:
        """Authentification par mot de passe (OAuth2 Password Grant)."""
        data = {
            "client_id": OAUTH_CLIENT_ID,
            "client_secret": OAUTH_CLIENT_SECRET,
            "user_prefix": OAUTH_USER_PREFIX,
            "grant_type": "password",
            "scope": OAUTH_SCOPE,
            "username": self._username,
            "password": self._password,
        }

        try:
            async with self._session.post(
                TOKEN_URL,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=TIMEOUT,
            ) as resp:
                if resp.status in (400, 401, 403):
                    body = await resp.text()
                    _LOGGER.error("Échec de connexion Intuis (%s): %s", resp.status, body)
                    raise IntuisAuthError(f"Identifiants invalides (HTTP {resp.status})")

                if resp.status != 200:
                    body = await resp.text()
                    raise IntuisConnectionError(f"Erreur API OAuth: HTTP {resp.status} - {body}")

                payload = await resp.json()
                self._access_token = payload.get("access_token")
                self._refresh_token = payload.get("refresh_token")
                expires_in = int(payload.get("expires_in", 3600))
                # On retire 120s de marge de sécurité
                self._token_expires_at = time.time() + max(60, expires_in - 120)

                if not self._access_token:
                    raise IntuisAuthError("Aucun jeton d'accès retourné par l'API")

        except aiohttp.ClientError as err:
            raise IntuisConnectionError(f"Erreur de communication avec l'API: {err}") from err
        except TimeoutError as err:
            raise IntuisConnectionError("Délai d'attente dépassé lors de l'authentification") from err

    async def async_refresh_token_if_needed(self) -> None:
        """Rafraîchit le token s'il est expiré ou sur le point d'expirer."""
        if self.is_authenticated:
            return

        if self._refresh_token:
            data = {
                "client_id": OAUTH_CLIENT_ID,
                "client_secret": OAUTH_CLIENT_SECRET,
                "grant_type": "refresh_token",
                "refresh_token": self._refresh_token,
                "user_prefix": OAUTH_USER_PREFIX,
            }
            try:
                async with self._session.post(
                    TOKEN_URL,
                    data=data,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    timeout=TIMEOUT,
                ) as resp:
                    if resp.status == 200:
                        payload = await resp.json()
                        self._access_token = payload.get("access_token")
                        self._refresh_token = payload.get("refresh_token", self._refresh_token)
                        expires_in = int(payload.get("expires_in", 3600))
                        self._token_expires_at = time.time() + max(60, expires_in - 120)
                        return
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("Échec du refresh_token, tentative de re-login complet: %s", err)

        await self.async_login()

    async def _request(
        self,
        method: str,
        url: str,
        json_data: dict[str, Any] | None = None,
        retry: bool = True,
    ) -> dict[str, Any]:
        """Exécute une requête authentifiée avec réessai en cas d'expiration de token."""
        await self.async_refresh_token_if_needed()

        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
        }

        try:
            async with self._session.request(
                method,
                url,
                json=json_data,
                headers=headers,
                timeout=TIMEOUT,
            ) as resp:
                if resp.status == 401 and retry:
                    _LOGGER.info("Token expiré lors de la requête %s, re-tentative...", url)
                    self._access_token = None
                    await self.async_login()
                    return await self._request(method, url, json_data, retry=False)

                if resp.status == 401:
                    raise IntuisAuthError("Authentification non autorisée (401)")

                if resp.status != 200:
                    text = await resp.text()
                    raise IntuisError(f"Erreur API ({resp.status}) sur {url}: {text}")

                return await resp.json()
        except aiohttp.ClientError as err:
            raise IntuisConnectionError(f"Erreur réseau sur {url}: {err}") from err
        except TimeoutError as err:
            raise IntuisConnectionError(f"Timeout lors de l'appel à {url}") from err

    async def async_get_homes(self) -> list[dict[str, Any]]:
        """Récupère la liste des habitations configurées sur le compte."""
        res = await self._request("GET", HOMES_DATA_URL)
        return res.get("body", {}).get("homes", [])

    async def async_get_home_status(self, home_id: str) -> dict[str, Any] | None:
        """Récupère l'état temps-réel (températures, consigne, chauffe) d'une maison."""
        try:
            res = await self._request("POST", HOME_STATUS_URL, json_data={"home_id": home_id})
            return res.get("body", {}).get("home")
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Impossible de récupérer homestatus pour %s: %s", home_id, err)
            return None

    async def async_get_room_measure(
        self,
        home_id: str,
        room_id: str,
        bridge_mac: str,
        start_ts: int,
        end_ts: int,
        scale: str = "1hour",
    ) -> dict[str, Any] | None:
        """Récupère les mesures d'énergie d'une pièce."""
        measure_type = (
            "sum_energy_elec,sum_energy_elec$0,sum_energy_elec$1,sum_energy_elec$2,"
            "sum_energy_price,sum_energy_price$0,sum_energy_price$1,sum_energy_price$2,"
            "sum_energy_elec_heating"
        )

        payload = {
            "app_type": "app_muller",
            "date_begin": int(start_ts),
            "date_end": int(end_ts),
            "app_version": APP_VERSION,
            "scale": scale,
            "home": {
                "id": home_id,
                "rooms": [
                    {
                        "id": room_id,
                        "bridge": bridge_mac,
                        "type": measure_type,
                    }
                ],
            },
        }

        try:
            res = await self._request("POST", GET_MEASURE_URL, json_data=payload)
            return res
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("Erreur lors de la récupération des mesures pour la pièce %s: %s", room_id, err)
            return None
