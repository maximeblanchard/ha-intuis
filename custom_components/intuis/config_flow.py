"""Config Flow pour l'intégration Intuis Connect."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import IntuisApi, IntuisAuthError, IntuisConnectionError, IntuisError
from .const import (
    CONF_BRIDGE_MAC,
    CONF_HOME_ID,
    CONF_HOME_NAME,
    CONF_HP_END,
    CONF_HP_START,
    CONF_SCAN_INTERVAL,
    DEFAULT_HP_END,
    DEFAULT_HP_START,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


class IntuisConfigFlow(ConfigFlow, domain=DOMAIN):
    """Gère le flux de configuration pour Intuis Connect."""

    VERSION = 1

    def __init__(self) -> None:
        self._email: str = ""
        self._password: str = ""
        self._homes: list[dict[str, Any]] = []

    async def _async_fetch_homes(
        self, email: str, password: str
    ) -> tuple[list[dict[str, Any]], str | None]:
        """Tente de se connecter à l'API et retourne la liste des logements."""
        session = async_create_clientsession(self.hass)
        api = IntuisApi(session, email, password)

        try:
            await api.async_login()
            homes = await api.async_get_homes()
        except IntuisAuthError:
            return [], "invalid_auth"
        except IntuisConnectionError as err:
            _LOGGER.debug("Erreur de connexion Intuis: %s", err)
            return [], "cannot_connect"
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Erreur inattendue lors de la configuration Intuis")
            return [], "unknown"

        if not homes:
            return [], "no_homes"

        return homes, None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Première étape : saisie des identifiants."""
        errors: dict[str, str] = {}

        if user_input is not None:
            homes, error = await self._async_fetch_homes(
                user_input[CONF_EMAIL], user_input[CONF_PASSWORD]
            )

            if error:
                errors["base"] = error
            else:
                self._email = user_input[CONF_EMAIL]
                self._password = user_input[CONF_PASSWORD]
                self._homes = homes

                if len(homes) == 1:
                    return await self._async_create_home_entry(homes[0])

                return await self.async_step_home()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_home(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Étape de sélection du logement si plusieurs sont présents."""
        if user_input is not None:
            selected_home_id = str(user_input[CONF_HOME_ID])
            home = next(
                (h for h in self._homes if str(h.get("id")) == selected_home_id),
                None,
            )
            if home:
                return await self._async_create_home_entry(home)

        choices = {
            str(h.get("id")): h.get("name") or f"Maison {h.get('id')}"
            for h in self._homes
        }

        return self.async_show_form(
            step_id="home",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOME_ID): vol.In(choices),
                }
            ),
        )

    async def _async_create_home_entry(self, home: dict[str, Any]) -> ConfigFlowResult:
        """Crée l'entrée de configuration finale."""
        home_id = str(home["id"])
        home_name = home.get("name") or "Maison"

        await self.async_set_unique_id(home_id)
        self._abort_if_unique_id_configured()

        # Recherche automatique du bridge MAC
        bridge_mac = None
        for mod in home.get("modules", []):
            if mod.get("type") in ("NLG", "bridge") or mod.get("bridge"):
                bridge_mac = mod.get("bridge") or mod.get("id")
                break
        if not bridge_mac and home.get("modules"):
            bridge_mac = home["modules"][0].get("id")

        return self.async_create_entry(
            title=f"Intuis {home_name}",
            data={
                CONF_EMAIL: self._email,
                CONF_PASSWORD: self._password,
                CONF_HOME_ID: home_id,
                CONF_HOME_NAME: home_name,
                CONF_BRIDGE_MAC: bridge_mac,
                CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
                CONF_HP_START: DEFAULT_HP_START,
                CONF_HP_END: DEFAULT_HP_END,
            },
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Gestion du déclenchement de réauthentification."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Formulaire de mise à jour des identifiants."""
        errors: dict[str, str] = {}
        reauth_entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])

        if user_input is not None and reauth_entry:
            email = user_input[CONF_EMAIL]
            password = user_input[CONF_PASSWORD]

            session = async_create_clientsession(self.hass)
            api = IntuisApi(session, email, password)

            try:
                await api.async_login()
                self.hass.config_entries.async_update_entry(
                    reauth_entry,
                    data={
                        **reauth_entry.data,
                        CONF_EMAIL: email,
                        CONF_PASSWORD: password,
                    },
                )
                await self.hass.config_entries.async_reload(reauth_entry.entry_id)
                return self.async_abort(reason="reauth_successful")
            except IntuisAuthError:
                errors["base"] = "invalid_auth"
            except Exception:  # noqa: BLE001
                errors["base"] = "cannot_connect"

        default_email = reauth_entry.data.get(CONF_EMAIL, "") if reauth_entry else ""

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_EMAIL, default=default_email): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Obtient le gestionnaire d'options."""
        return IntuisOptionsFlowHandler()


class IntuisOptionsFlowHandler(OptionsFlow):
    """Gère le formulaire d'options (intervalle de scan, plages HP/HC)."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Affiche et sauvegarde les options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        entry = self.config_entry
        current_interval = entry.options.get(
            CONF_SCAN_INTERVAL, entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        )
        current_hp_start = entry.options.get(
            CONF_HP_START, entry.data.get(CONF_HP_START, DEFAULT_HP_START)
        )
        current_hp_end = entry.options.get(
            CONF_HP_END, entry.data.get(CONF_HP_END, DEFAULT_HP_END)
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=current_interval,
                    ): vol.All(vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL)),
                    vol.Required(
                        CONF_HP_START,
                        default=current_hp_start,
                    ): vol.All(vol.Coerce(int), vol.Range(min=0, max=23)),
                    vol.Required(
                        CONF_HP_END,
                        default=current_hp_end,
                    ): vol.All(vol.Coerce(int), vol.Range(min=0, max=23)),
                }
            ),
        )
