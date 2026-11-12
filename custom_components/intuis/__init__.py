"""Intégration Intuis Connect pour Home Assistant."""

from __future__ import annotations

from datetime import datetime
import logging

from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.event import async_track_time_change

from .api import IntuisApi
from .coordinator import IntuisConfigEntry, IntuisCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: IntuisConfigEntry) -> bool:
    """Configuration d'une entrée Intuis Connect."""
    session = async_create_clientsession(hass)
    api = IntuisApi(session, entry.data[CONF_EMAIL], entry.data[CONF_PASSWORD])

    coordinator = IntuisCoordinator(hass, entry, api)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    # Rafraîchissement automatique planifié à 23h59 pour figer les données de la journée
    @callback
    def _async_end_of_day_refresh(now: datetime) -> None:
        _LOGGER.info("Déclenchement du rafraîchissement Intuis de fin de journée (23h59)")
        entry.async_create_task(hass, coordinator.async_request_refresh())

    entry.async_on_unload(
        async_track_time_change(
            hass,
            _async_end_of_day_refresh,
            hour=23,
            minute=59,
            second=0,
        )
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def _async_reload(hass: HomeAssistant, entry: IntuisConfigEntry) -> None:
    """Recharge l'intégration lors d'un changement d'options."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: IntuisConfigEntry) -> bool:
    """Décharge l'intégration."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
