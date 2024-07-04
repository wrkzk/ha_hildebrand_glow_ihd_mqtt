"""Support for hildebrand glow MQTT sensors."""

from __future__ import annotations

import json
import re
import logging
from typing import Iterable

from homeassistant.components import mqtt
from homeassistant.components.mqtt.models import ReceiveMessage
from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from .const import DOMAIN, CONF_TOPIC_PREFIX
from homeassistant.const import (
    CONF_DEVICE_ID,
    ATTR_DEVICE_ID,
    UnitOfEnergy,
    UnitOfVolume,
    UnitOfPower,
    UnitOfTemperature,
    SIGNAL_STRENGTH_DECIBELS,
)
from homeassistant.core import callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.util import slugify

_LOGGER = logging.getLogger(__name__)

# glow/XXXXXXYYYYYY/STATE                   {"software":"v1.8.12","timestamp":"2022-06-11T20:54:53Z","hardware":"GLOW-IHD-01-1v4-SMETS2","ethmac":"1234567890AB","smetsversion":"SMETS2","eui":"12:34:56:78:91:23:45","zigbee":"1.2.5","han":{"rssi":-75,"status":"joined","lqi":100}}
# glow/XXXXXXYYYYYY/SENSOR/electricitymeter {"electricitymeter":{"timestamp":"2022-06-11T20:38:00Z","energy":{"export":{"cumulative":0.000,"units":"kWh"},"import":{"cumulative":6613.405,"day":13.252,"week":141.710,"month":293.598,"units":"kWh","mpan":"1234","supplier":"ABC ENERGY","price":{"unitrate":0.04998,"standingcharge":0.24030}}},"power":{"value":0.951,"units":"kW"}}}
# glow/XXXXXXYYYYYY/SENSOR/gasmeter         {"gasmeter":{"timestamp":"2022-06-11T20:53:52Z","energy":{"export":{"cumulative":0.000,"units":"kWh"},"import":{"cumulative":17940.852,"day":11.128,"week":104.749,"month":217.122,"units":"kWh","mprn":"1234","supplier":"---","price":{"unitrate":0.07320,"standingcharge":0.17850}}},"power":{"value":0.000,"units":"kW"}}}

device_types = {}

STATE_SENSORS = [
    {
        "name": "Smart Meter IHD Software Version",
        "device_class": None,
        "unit_of_measurement": None,
        "state_class": None,
        # "entity_category": EntityCategory.DIAGNOSTIC,
        "icon": "mdi:information-outline",
        "func": lambda js: js["software"],
    },
    {
        "name": "Smart Meter IHD Hardware",
        "device_class": None,
        "unit_of_measurement": None,
        "state_class": None,
        # "entity_category": EntityCategory.DIAGNOSTIC,
        "icon": "mdi:information-outline",
        "func": lambda js: js["hardware"],
    },
    {
        "name": "Smart Meter IHD HAN Status",
        "device_class": None,
        "unit_of_measurement": None,
        "state_class": None,
        # "entity_category": EntityCategory.DIAGNOSTIC,
        "icon": "mdi:information-outline",
        "func": lambda js: js["han"]["status"],
    },
    {
        "name": "Smart Meter IHD HAN RSSI",
        "device_class": SensorDeviceClass.SIGNAL_STRENGTH,
        "unit_of_measurement": SIGNAL_STRENGTH_DECIBELS,
        "state_class": SensorStateClass.MEASUREMENT,
        # "entity_category": EntityCategory.DIAGNOSTIC,
        "icon": "mdi:wifi-strength-outline",
        "func": lambda js: js["han"]["rssi"],
    },
    {
        "name": "Smart Meter IHD HAN LQI",
        "device_class": None,
        "unit_of_measurement": None,
        "state_class": SensorStateClass.MEASUREMENT,
        # "entity_category": EntityCategory.DIAGNOSTIC,
        "icon": "mdi:wifi-strength-outline",
        "func": lambda js: js["han"]["lqi"],
    },
]

ELECTRICITY_SENSORS = [
    {
        "name": "Smart Meter Electricity: Export",
        "device_class": SensorDeviceClass.ENERGY,
        "unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "icon": "mdi:flash",
        "func": lambda js: js["electricitymeter"]["energy"]["export"]["cumulative"],
    },
    {
        "name": "Smart Meter Electricity: Import",
        "device_class": SensorDeviceClass.ENERGY,
        "unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "icon": "mdi:flash",
        "func": lambda js: js["electricitymeter"]["energy"]["import"]["cumulative"],
        "ignore_zero_values": True,
    },
    {
        "name": "Smart Meter Electricity: Import (Today)",
        "device_class": SensorDeviceClass.ENERGY,
        "unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "icon": "mdi:flash",
        "func": lambda js: js["electricitymeter"]["energy"]["import"]["day"],
    },
    {
        "name": "Smart Meter Electricity: Import (This week)",
        "device_class": SensorDeviceClass.ENERGY,
        "unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "icon": "mdi:flash",
        "func": lambda js: js["electricitymeter"]["energy"]["import"]["week"],
    },
    {
        "name": "Smart Meter Electricity: Import (This month)",
        "device_class": SensorDeviceClass.ENERGY,
        "unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "icon": "mdi:flash",
        "func": lambda js: js["electricitymeter"]["energy"]["import"]["month"],
    },
    {
        "name": "Smart Meter Electricity: Import Unit Rate",
        "device_class": SensorDeviceClass.MONETARY,
        "unit_of_measurement": "GBP/kWh",
        "state_class": None,
        "icon": "mdi:cash",
        "func": lambda js: js["electricitymeter"]["energy"]["import"]["price"][
            "unitrate"
        ],
        "ignore_zero_values": True,
    },
    {
        "name": "Smart Meter Electricity: Import Standing Charge",
        "device_class": SensorDeviceClass.MONETARY,
        "unit_of_measurement": "GBP",
        "state_class": None,
        "icon": "mdi:cash",
        "func": lambda js: js["electricitymeter"]["energy"]["import"]["price"][
            "standingcharge"
        ],
        "ignore_zero_values": True,
    },
    {
        "name": "Smart Meter Electricity: Power",
        "device_class": SensorDeviceClass.POWER,
        "unit_of_measurement": UnitOfPower.KILO_WATT,
        "state_class": SensorStateClass.MEASUREMENT,
        "icon": "mdi:flash",
        "func": lambda js: js["electricitymeter"]["power"]["value"],
    },
    {
        "name": "Smart Meter Electricity: Cost (Today)",
        "device_class": SensorDeviceClass.MONETARY,
        "unit_of_measurement": "GBP",
        "state_class": SensorStateClass.TOTAL,
        "icon": "mdi:cash",
        "func": lambda js: round(
            js["electricitymeter"]["energy"]["import"]["price"]["standingcharge"]
            + (
                js["electricitymeter"]["energy"]["import"]["day"]
                * js["electricitymeter"]["energy"]["import"]["price"]["unitrate"]
            ),
            2,
        ),
    },
]

THERMAL_SENSORS = [
    {
        "name": "Current Temperature",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "unit_of_measurement": UnitOfTemperature.CELSIUS,
        "state_class": SensorStateClass.MEASUREMENT,
        "suggested_display_precision": 1,
        "icon": "mdi:thermometer",
        "func": lambda js, name, id: js[name][id]["temperature"]["value"],
        "ignore_zero_values": False,
        "thermal": True,
    },
    {
        "name": "Current Humidity",
        "device_class": SensorDeviceClass.HUMIDITY,
        "unit_of_measurement": "%",
        "state_class": SensorStateClass.MEASUREMENT,
        "icon": "mdi:water-percent",
        "func": lambda js, name, id: js[name][id]["humidity"]["value"],
        "ignore_zero_values": False,
        "thermal": True,
    },
    {
        "name": "Current Battery",
        "device_class": SensorDeviceClass.BATTERY,
        "unit_of_measurement": "%",
        "state_class": SensorStateClass.MEASUREMENT,
        "icon": "mdi:battery",
        "func": lambda js, name, id: js[name][id]["battery"]["value"],
        "ignore_zero_values": False,
        "thermal": True,
    },
    {
        "name": "Hardware Address",
        "device_class": None,
        "unit_of_measurement": None,
        "state_class": None,
        # "entity_category": EntityCategory.DIAGNOSTIC,
        "icon": "mdi:information-outline",
        "func": lambda js, name, id: ":".join(
            [id[i : i + 2] for i in range(0, len(id), 2)]
        ),
        "ignore_zero_values": False,
        "thermal": True,
    },
]

GAS_SENSORS = [
    {
        "name": "Smart Meter Gas: Import",
        "device_class": SensorDeviceClass.ENERGY,
        "unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "icon": "mdi:fire",
        "func": lambda js: js["gasmeter"]["energy"]["import"]["cumulative"],
        "ignore_zero_values": True,
    },
    {
        "name": "Smart Meter Gas: Import Vol",
        "device_class": SensorDeviceClass.GAS,
        "unit_of_measurement": UnitOfVolume.CUBIC_METERS,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "icon": "mdi:fire",
        "func": lambda js: js["gasmeter"]["energy"]["import"]["cumulativevol"],
        "ignore_zero_values": True,
    },
    {
        "name": "Smart Meter Gas: Import Vol (Today)",
        "device_class": SensorDeviceClass.ENERGY,  # Change this to GAS if cubic meters is used
        "unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR,  # Might change to VOLUME_CUBIC_METERS soon
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "icon": "mdi:fire",
        "func": lambda js: js["gasmeter"]["energy"]["import"]["dayvol"],
    },
    {
        "name": "Smart Meter Gas: Import Vol (This week)",
        "device_class": SensorDeviceClass.ENERGY,  # Change this to GAS if cubic meters is used
        "unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR,  # Might change to VOLUME_CUBIC_METERS soon
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "icon": "mdi:fire",
        "func": lambda js: js["gasmeter"]["energy"]["import"]["weekvol"],
    },
    {
        "name": "Smart Meter Gas: Import Vol (This month)",
        "device_class": SensorDeviceClass.ENERGY,  # Change this to GAS if cubic meters is used
        "unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR,  # Might change to VOLUME_CUBIC_METERS soon
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "icon": "mdi:fire",
        "func": lambda js: js["gasmeter"]["energy"]["import"]["monthvol"],
    },
    {
        "name": "Smart Meter Gas: Import (Today)",
        "device_class": SensorDeviceClass.ENERGY,
        "unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "icon": "mdi:fire",
        "func": lambda js: js["gasmeter"]["energy"]["import"]["day"],
    },
    {
        "name": "Smart Meter Gas: Import (This week)",
        "device_class": SensorDeviceClass.ENERGY,
        "unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "icon": "mdi:fire",
        "func": lambda js: js["gasmeter"]["energy"]["import"]["week"],
    },
    {
        "name": "Smart Meter Gas: Import (This month)",
        "device_class": SensorDeviceClass.ENERGY,
        "unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "icon": "mdi:fire",
        "func": lambda js: js["gasmeter"]["energy"]["import"]["month"],
    },
    {
        "name": "Smart Meter Gas: Import Unit Rate",
        "device_class": SensorDeviceClass.MONETARY,
        "unit_of_measurement": "GBP/kWh",
        "state_class": None,
        "icon": "mdi:cash",
        "func": lambda js: js["gasmeter"]["energy"]["import"]["price"]["unitrate"],
        "ignore_zero_values": True,
    },
    {
        "name": "Smart Meter Gas: Import Standing Charge",
        "device_class": SensorDeviceClass.MONETARY,
        "unit_of_measurement": "GBP",
        "state_class": None,
        "icon": "mdi:cash",
        "func": lambda js: js["gasmeter"]["energy"]["import"]["price"][
            "standingcharge"
        ],
        "ignore_zero_values": True,
    },
    # Removed June 2022 in IHD software update 1.8.13
    # {
    #   "name": "Smart Meter Gas: Power",
    #   "device_class": SensorDeviceClass.POWER,
    #   "unit_of_measurement": UnitOfPower.KILO_WATT,
    #   "state_class": SensorStateClass.MEASUREMENT,
    #   "icon": "mdi:fire",
    #   "func": lambda js : js['gasmeter']['power']['value'],
    # },
    {
        "name": "Smart Meter Gas: Cost (Today)",
        "device_class": SensorDeviceClass.MONETARY,
        "unit_of_measurement": "GBP",
        "state_class": SensorStateClass.TOTAL,
        "icon": "mdi:cash",
        "func": lambda js: round(
            (js["gasmeter"]["energy"]["import"]["price"]["standingcharge"] or 0)
            + (
                (js["gasmeter"]["energy"]["import"]["day"] or 0)
                * (js["gasmeter"]["energy"]["import"]["price"]["unitrate"] or 0)
            ),
            2,
        ),
    },
]


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the Smart Meter sensors."""

    # the config is defaulted to + which happens to mean we will subscribe to all devices
    device_mac = hass.data[DOMAIN][config_entry.entry_id][CONF_DEVICE_ID]
    topic_prefix = hass.data[DOMAIN][config_entry.entry_id][CONF_TOPIC_PREFIX] or "glow"

    deviceUpdateGroups = {}
    thermal_sensor_ids = []

    @callback
    async def mqtt_message_received(message: ReceiveMessage):
        """Handle received MQTT message."""
        topic = message.topic
        payload = message.payload
        device_id = topic.split("/")[1]

        if len(topic.split("/")) >= 5:
            if topic.split("/")[3][0:12] == "glowsensorth":
                thermal_sensor_ids.append(topic.split("/")[4])
                device_id = topic.split("/")[3] + "/" + topic.split("/")[4]

        if device_mac == "+" or device_id == device_mac:
            updateGroups = await async_get_device_groups(
                deviceUpdateGroups, async_add_entities, device_id
            )
            _LOGGER.debug("Received message: %s", topic)
            _LOGGER.debug("  Payload: %s", payload)
            for updateGroup in updateGroups:
                updateGroup.process_update(message)

    data_topic = f"{topic_prefix}/#"

    await mqtt.async_subscribe(hass, data_topic, mqtt_message_received, 1)


def num_of_thermal_sensors() -> int:
    count = 0
    for value in device_types.values():
        if len(value) > 1:
            count += 1
    return count


async def async_get_device_groups(deviceUpdateGroups, async_add_entities, device_id):
    # add to update groups if not already there
    if device_id not in deviceUpdateGroups:
        _LOGGER.debug("New device found: %s", device_id)

        groups = []

        if device_id.split("/")[0] == "glowsensorth1":
            device_types[device_id.split("/")[1]] = [
                "Hildebrand Thermal Sensor " + str(num_of_thermal_sensors() + 1),
                device_id.split("/")[0],
            ]
            groups = [
                HildebrandGlowMqttSensorUpdateGroup(
                    device_id.split("/")[1],
                    device_id.split("/")[1],
                    THERMAL_SENSORS,
                ),
            ]

        else:
            device_types[device_id] = ["Hildebrand Glow Hub"]
            groups = [
                HildebrandGlowMqttSensorUpdateGroup(device_id, "STATE", STATE_SENSORS),
                HildebrandGlowMqttSensorUpdateGroup(
                    device_id, "electricitymeter", ELECTRICITY_SENSORS
                ),
                # HildebrandGlowMqttSensorUpdateGroup(device_id, "gasmeter", GAS_SENSORS),
            ]

        async_add_entities(
            [
                sensorEntity
                for updateGroup in groups
                for sensorEntity in updateGroup.all_sensors
            ],
            # True
        )
        deviceUpdateGroups[device_id] = groups

    return deviceUpdateGroups[device_id]


class HildebrandGlowMqttSensorUpdateGroup:
    """Representation of Hildebrand Glow MQTT Meter Sensors that all get updated together."""

    def __init__(self, device_id: str, topic_regex: str, meters: Iterable) -> None:
        """Initialize the sensor collection."""
        self._topic_regex = re.compile(topic_regex)
        self._sensors = [
            HildebrandGlowMqttSensor(device_id=device_id, **meter) for meter in meters
        ]

    def process_update(self, message: ReceiveMessage) -> None:
        """Process an update from the MQTT broker."""
        topic = message.topic
        payload = message.payload
        if self._topic_regex.search(topic):
            _LOGGER.debug("Matched on %s", self._topic_regex.pattern)
            parsed_data = json.loads(payload)
            for sensor in self._sensors:
                sensor.process_update(parsed_data)

    @property
    def all_sensors(self) -> Iterable[HildebrandGlowMqttSensor]:
        """Return all meters."""
        return self._sensors


class HildebrandGlowMqttSensor(SensorEntity):
    """Representation of a room sensor that is updated via MQTT."""

    def __init__(
        self,
        device_id,
        name,
        icon,
        device_class,
        unit_of_measurement,
        state_class,
        func,
        thermal=False,
        entity_category=None,
        ignore_zero_values=False,
        suggested_display_precision=None,
    ) -> None:
        """Initialize the sensor."""
        self._device_id = device_id
        self._ignore_zero_values = ignore_zero_values
        self._attr_suggested_display_precision = suggested_display_precision
        self._attr_name = name
        self._attr_unique_id = slugify(device_id + "_" + name)
        self._attr_icon = icon
        if device_class:
            self._attr_device_class = device_class
        if unit_of_measurement:
            self._attr_native_unit_of_measurement = unit_of_measurement
        if state_class:
            self._attr_state_class = state_class
        self._attr_entity_category = entity_category
        self._attr_should_poll = False

        self._func = func
        self._thermal = thermal

        if self._thermal:
            self._attr_device_info = DeviceInfo(
                connections={("mac", device_id)},
                manufacturer="Hildebrand Technology Limited",
                model="Glow Thermal Sensor",
                name=device_types[device_id][0],
            )
        else:
            self._attr_device_info = DeviceInfo(
                connections={("mac", device_id)},
                manufacturer="Hildebrand Technology Limited",
                model="Glow Smart Hub",
                name=device_types[device_id][0] + " " + device_id,
            )

        self._attr_native_value = None

    def process_update(self, mqtt_data) -> None:
        """Update the state of the sensor."""
        if self._thermal:
            new_value = self._func(
                mqtt_data, device_types[self._device_id][1], self._device_id
            )
        else:
            new_value = self._func(mqtt_data)

        if self._ignore_zero_values and new_value == 0:
            _LOGGER.debug(
                "Ignored new value of %s on %s.", new_value, self._attr_unique_id
            )
            return
        self._attr_native_value = new_value
        if (
            self.hass is not None
        ):  # this is a hack to get around the fact that the entity is not yet initialized at first
            self.async_schedule_update_ha_state()

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return {ATTR_DEVICE_ID: self._device_id}
