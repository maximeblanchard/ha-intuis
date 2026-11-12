"""Coordinateur de mise à jour des données pour Intuis Connect."""

from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

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
)

_LOGGER = logging.getLogger(__name__)

type IntuisConfigEntry = ConfigEntry[IntuisCoordinator]


class IntuisCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Gère le rafraîchissement régulier des données des radiateurs Intuis."""

    config_entry: IntuisConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: IntuisConfigEntry,
        api: IntuisApi,
    ) -> None:
        self.api = api
        self.home_id = entry.data[CONF_HOME_ID]
        self.home_name = entry.data.get(CONF_HOME_NAME, "Intuis")
        self.bridge_mac: str | None = entry.data.get(CONF_BRIDGE_MAC)

        scan_interval_min = entry.options.get(
            CONF_SCAN_INTERVAL,
            entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{self.home_id}",
            update_interval=timedelta(minutes=scan_interval_min),
        )

    def _get_hp_bounds(self) -> tuple[int, int]:
        """Retourne les heures de début et fin des Heures Pleines."""
        hp_start = self.config_entry.options.get(
            CONF_HP_START,
            self.config_entry.data.get(CONF_HP_START, DEFAULT_HP_START),
        )
        hp_end = self.config_entry.options.get(
            CONF_HP_END,
            self.config_entry.data.get(CONF_HP_END, DEFAULT_HP_END),
        )
        return int(hp_start), int(hp_end)

    async def _async_update_data(self) -> dict[str, Any]:
        """Récupère l'état complet des pièces et radiateurs depuis l'API Intuis."""
        try:
            # 1. Récupération des informations du domicile et des pièces
            homes = await self.api.async_get_homes()
            home = next((h for h in homes if str(h.get("id")) == str(self.home_id)), None)

            if not home and homes:
                home = homes[0]
                self.home_id = str(home.get("id"))
                _LOGGER.warning("Domicile configuré introuvable, utilisation de %s", self.home_id)

            if not home:
                raise UpdateFailed("Aucun domicile trouvé sur le compte Intuis")

            # 2. Détection dynamique de l'adresse MAC du bridge
            if not self.bridge_mac:
                for mod in home.get("modules", []):
                    if mod.get("type") in ("NLG", "bridge") or mod.get("bridge"):
                        self.bridge_mac = mod.get("bridge") or mod.get("id")
                        break
                # Fallback sur le premier module disponible
                if not self.bridge_mac and home.get("modules"):
                    self.bridge_mac = home["modules"][0].get("id")

            # 3. Récupération de l'état temps-réel (températures, consigne, chauffe)
            live_status = await self.api.async_get_home_status(self.home_id)
            live_rooms_map: dict[str, dict[str, Any]] = {}
            if live_status and "rooms" in live_status:
                live_rooms_map = {str(r.get("id")): r for r in live_status.get("rooms", [])}

            # 4. Calcul des fenêtres temporelles
            now = dt_util.now()
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            today_start_ts = int(today_start.timestamp())
            today_end_ts = int(now.timestamp())

            yesterday = now - timedelta(days=1)
            yesterday_start = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
            yesterday_end = yesterday.replace(hour=23, minute=59, second=59, microsecond=0)
            yesterday_start_ts = int(yesterday_start.timestamp())
            yesterday_end_ts = int(yesterday_end.timestamp())

            month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            month_start_ts = int(month_start.timestamp())
            month_end_ts = today_end_ts

            hp_start, hp_end = self._get_hp_bounds()

            rooms_data: dict[str, dict[str, Any]] = {}
            totals = {
                "today_total": 0.0,
                "today_hp": 0.0,
                "today_hc": 0.0,
                "yesterday_total": 0.0,
                "yesterday_hp": 0.0,
                "yesterday_hc": 0.0,
                "month_total": 0.0,
            }

            # 5. Pour chaque pièce, récupération et calcul des consommations
            for room in home.get("rooms", []):
                room_id = str(room.get("id"))
                room_name = room.get("name", f"Pièce {room_id}")
                room_type = room.get("type", "room")

                # Détermination du bridge associé à la pièce si possible
                room_bridge = self.bridge_mac
                for mod_id in room.get("module_ids", []):
                    for m in home.get("modules", []):
                        if m.get("id") == mod_id and m.get("bridge"):
                            room_bridge = m.get("bridge")
                            break

                # a. Consommation aujourd'hui
                today_res = await self.api.async_get_room_measure(
                    self.home_id, room_id, room_bridge or "", today_start_ts, today_end_ts, scale="1hour"
                )
                today_hp, today_hc, today_total = self._parse_measures(today_res, hp_start, hp_end)

                # b. Consommation hier
                yesterday_res = await self.api.async_get_room_measure(
                    self.home_id, room_id, room_bridge or "", yesterday_start_ts, yesterday_end_ts, scale="1hour"
                )
                yesterday_hp, yesterday_hc, yesterday_total = self._parse_measures(yesterday_res, hp_start, hp_end)

                # c. Consommation mensuelle
                month_res = await self.api.async_get_room_measure(
                    self.home_id, room_id, room_bridge or "", month_start_ts, month_end_ts, scale="1day"
                )
                _, _, month_total = self._parse_measures(month_res, 0, 24)

                # d. Données temps-réel (status)
                live_info = live_rooms_map.get(room_id, {})
                current_temp = live_info.get("therm_measured_temperature")
                setpoint_temp = live_info.get("therm_setpoint_temperature")
                heating_power = live_info.get("heating_power_request")
                hvac_mode = live_info.get("therm_setpoint_mode")

                rooms_data[room_id] = {
                    "id": room_id,
                    "name": room_name,
                    "type": room_type,
                    "bridge": room_bridge,
                    "today_total": round(today_total, 1),
                    "today_hp": round(today_hp, 1),
                    "today_hc": round(today_hc, 1),
                    "yesterday_total": round(yesterday_total, 1),
                    "yesterday_hp": round(yesterday_hp, 1),
                    "yesterday_hc": round(yesterday_hc, 1),
                    "month_total_wh": round(month_total, 1),
                    "month_total_kwh": round(month_total / 1000.0, 2),
                    "current_temperature": current_temp,
                    "setpoint_temperature": setpoint_temp,
                    "heating_power": heating_power,
                    "is_heating": bool(heating_power and heating_power > 0),
                    "hvac_mode": hvac_mode,
                }

                # Cumul global
                totals["today_total"] += today_total
                totals["today_hp"] += today_hp
                totals["today_hc"] += today_hc
                totals["yesterday_total"] += yesterday_total
                totals["yesterday_hp"] += yesterday_hp
                totals["yesterday_hc"] += yesterday_hc
                totals["month_total"] += month_total

            # Arrondis globaux
            for k in totals:
                totals[k] = round(totals[k], 1)
            totals["month_total_kwh"] = round(totals["month_total"] / 1000.0, 2)

            return {
                "home_id": self.home_id,
                "home_name": self.home_name,
                "bridge_mac": self.bridge_mac,
                "rooms": rooms_data,
                "totals": totals,
                "last_update": now,
            }

        except IntuisAuthError as err:
            raise ConfigEntryAuthFailed(f"Session Intuis expirée ou invalide: {err}") from err
        except IntuisConnectionError as err:
            raise UpdateFailed(f"Impossible de joindre l'API Intuis: {err}") from err
        except IntuisError as err:
            raise UpdateFailed(f"Erreur de l'API Intuis: {err}") from err
        except Exception as err:
            _LOGGER.exception("Erreur inattendue pendant la mise à jour Intuis")
            raise UpdateFailed(f"Erreur inattendue: {err}") from err

    @staticmethod
    def _parse_measures(
        data: dict[str, Any] | None,
        hp_start: int,
        hp_end: int,
    ) -> tuple[float, float, float]:
        """Calcule HP, HC et Total (Wh) à partir de la réponse de l'API gethomemeasure."""
        if not data or not isinstance(data, dict):
            return 0.0, 0.0, 0.0

        try:
            rooms = data.get("body", {}).get("home", {}).get("rooms", [])
            if not rooms:
                return 0.0, 0.0, 0.0

            measures = rooms[0].get("measures", [])
            if not measures:
                return 0.0, 0.0, 0.0

            values = measures[0].get("value", [])
            hp = 0.0
            hc = 0.0
            total = 0.0

            for hour_idx, val_entry in enumerate(values):
                val = 0.0
                if isinstance(val_entry, list) and val_entry:
                    try:
                        val = float(val_entry[0])
                    except (ValueError, TypeError):
                        val = 0.0
                elif isinstance(val_entry, (int, float)):
                    val = float(val_entry)

                hour = hour_idx % 24
                if hp_start <= hour <= hp_end:
                    hp += val
                else:
                    hc += val
                total += val

            return hp, hc, total
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Erreur lors de l'analyse des mesures Intuis: %s", err)
            return 0.0, 0.0, 0.0
