"""Capteurs pour l'intégration Intuis Connect."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfEnergy, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL_HUB, MODEL_RADIATOR
from .coordinator import IntuisConfigEntry, IntuisCoordinator


@dataclass(frozen=True, kw_only=True)
class IntuisRoomSensorDescription(SensorEntityDescription):
    """Description d'un capteur associé à un radiateur / une pièce."""

    value_fn: Callable[[dict[str, Any]], Any]
    available_fn: Callable[[dict[str, Any]], bool] | None = None


@dataclass(frozen=True, kw_only=True)
class IntuisHomeSensorDescription(SensorEntityDescription):
    """Description d'un capteur global du domicile."""

    value_fn: Callable[[dict[str, Any]], Any]


ROOM_SENSOR_DESCRIPTIONS: tuple[IntuisRoomSensorDescription, ...] = (
    IntuisRoomSensorDescription(
        key="today_total",
        translation_key="room_today_total",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=0,
        icon="mdi:radiator",
        value_fn=lambda r: r.get("today_total"),
    ),
    IntuisRoomSensorDescription(
        key="today_hp",
        translation_key="room_today_hp",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=0,
        icon="mdi:weather-sunny",
        value_fn=lambda r: r.get("today_hp"),
    ),
    IntuisRoomSensorDescription(
        key="today_hc",
        translation_key="room_today_hc",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=0,
        icon="mdi:weather-night",
        value_fn=lambda r: r.get("today_hc"),
    ),
    IntuisRoomSensorDescription(
        key="yesterday_total",
        translation_key="room_yesterday_total",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=0,
        icon="mdi:history",
        value_fn=lambda r: r.get("yesterday_total"),
    ),
    IntuisRoomSensorDescription(
        key="yesterday_hp",
        translation_key="room_yesterday_hp",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=0,
        icon="mdi:history",
        value_fn=lambda r: r.get("yesterday_hp"),
    ),
    IntuisRoomSensorDescription(
        key="yesterday_hc",
        translation_key="room_yesterday_hc",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=0,
        icon="mdi:history",
        value_fn=lambda r: r.get("yesterday_hc"),
    ),
    IntuisRoomSensorDescription(
        key="month_total",
        translation_key="room_month_total",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=2,
        icon="mdi:calendar-month",
        value_fn=lambda r: r.get("month_total_kwh"),
    ),
    IntuisRoomSensorDescription(
        key="temperature",
        translation_key="room_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda r: r.get("current_temperature"),
        available_fn=lambda r: r.get("current_temperature") is not None,
    ),
    IntuisRoomSensorDescription(
        key="setpoint",
        translation_key="room_setpoint",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        icon="mdi:thermometer-check",
        value_fn=lambda r: r.get("setpoint_temperature"),
        available_fn=lambda r: r.get("setpoint_temperature") is not None,
    ),
    IntuisRoomSensorDescription(
        key="heating_power",
        translation_key="room_heating_power",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:fire",
        value_fn=lambda r: r.get("heating_power"),
        available_fn=lambda r: r.get("heating_power") is not None,
    ),
)

HOME_SENSOR_DESCRIPTIONS: tuple[IntuisHomeSensorDescription, ...] = (
    IntuisHomeSensorDescription(
        key="home_today_total",
        translation_key="home_today_total",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=0,
        icon="mdi:home-lightning-bolt",
        value_fn=lambda totals: totals.get("today_total"),
    ),
    IntuisHomeSensorDescription(
        key="home_today_hp",
        translation_key="home_today_hp",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=0,
        icon="mdi:weather-sunny",
        value_fn=lambda totals: totals.get("today_hp"),
    ),
    IntuisHomeSensorDescription(
        key="home_today_hc",
        translation_key="home_today_hc",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=0,
        icon="mdi:weather-night",
        value_fn=lambda totals: totals.get("today_hc"),
    ),
    IntuisHomeSensorDescription(
        key="home_yesterday_total",
        translation_key="home_yesterday_total",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=0,
        icon="mdi:history",
        value_fn=lambda totals: totals.get("yesterday_total"),
    ),
    IntuisHomeSensorDescription(
        key="home_month_total",
        translation_key="home_month_total",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=2,
        icon="mdi:calendar-month",
        value_fn=lambda totals: totals.get("month_total_kwh"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IntuisConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Instancie les capteurs Intuis Connect."""
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = []

    # 1. Capteurs globaux du logement
    for desc in HOME_SENSOR_DESCRIPTIONS:
        entities.append(IntuisHomeSensor(coordinator, desc))

    # 2. Capteurs par radiateur / pièce
    rooms = coordinator.data.get("rooms", {})
    for room_id, room_info in rooms.items():
        for desc in ROOM_SENSOR_DESCRIPTIONS:
            entities.append(IntuisRoomSensor(coordinator, desc, room_id, room_info.get("name", "")))

    async_add_entities(entities)


class IntuisRoomSensor(CoordinatorEntity[IntuisCoordinator], SensorEntity):
    """Capteur associé à un radiateur / une pièce."""

    entity_description: IntuisRoomSensorDescription

    def __init__(
        self,
        coordinator: IntuisCoordinator,
        description: IntuisRoomSensorDescription,
        room_id: str,
        room_name: str,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self.room_id = room_id
        self._attr_has_entity_name = True
        self._attr_unique_id = f"{coordinator.home_id}_{room_id}_{description.key}"

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{coordinator.home_id}_{room_id}")},
            name=f"Radiateur {room_name}",
            manufacturer=MANUFACTURER,
            model=MODEL_RADIATOR,
            suggested_area=room_name,
            via_device=(DOMAIN, coordinator.home_id),
        )

    @property
    def _room_data(self) -> dict[str, Any]:
        """Données de la pièce issues du coordinateur."""
        return self.coordinator.data.get("rooms", {}).get(self.room_id, {})

    @property
    def native_value(self) -> Any:
        """Valeur du capteur."""
        return self.entity_description.value_fn(self._room_data)

    @property
    def available(self) -> bool:
        """Disponibilité du capteur."""
        if not super().available:
            return False
        if self.room_id not in self.coordinator.data.get("rooms", {}):
            return False
        if self.entity_description.available_fn:
            return self.entity_description.available_fn(self._room_data)
        return True


class IntuisHomeSensor(CoordinatorEntity[IntuisCoordinator], SensorEntity):
    """Capteur global du logement (somme de tous les radiateurs)."""

    entity_description: IntuisHomeSensorDescription

    def __init__(
        self,
        coordinator: IntuisCoordinator,
        description: IntuisHomeSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_has_entity_name = True
        self._attr_unique_id = f"{coordinator.home_id}_global_{description.key}"

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.home_id)},
            name=f"Logement {coordinator.home_name}",
            manufacturer=MANUFACTURER,
            model=MODEL_HUB,
        )

    @property
    def native_value(self) -> Any:
        """Valeur globale cumulée."""
        totals = self.coordinator.data.get("totals", {})
        return self.entity_description.value_fn(totals)
