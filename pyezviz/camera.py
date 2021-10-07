"""pyezviz camera api."""
from __future__ import annotations

import datetime
from typing import Any

from pyezviz.constants import DeviceCatagories, DeviceSwitchType, SoundMode
from pyezviz.exceptions import PyEzvizError


class EzvizCamera:
    """Initialize Ezviz camera object."""

    def __init__(self, client, serial: str, device_obj: dict | None = None) -> None:
        """Initialize the camera object."""
        self._client = client
        self._serial = serial
        self._switch: dict[int, bool] = {}
        self._alarmmotiontrigger: dict[str, Any] = {}
        self._device = device_obj or {}
        self.alarmlist_time = None
        self.alarmlist_pic = None

    def load(self) -> None:
        """Update device info for camera serial."""

        if self._device is None:
            self._device = self._client.get_all_per_serial_infos(self._serial)

        self._alarm_list()

        self._switch_status()

    def _switch_status(self) -> None:
        """load device switches"""

        if self._device.get("switchStatusInfos"):
            for switch in self._device["switchStatusInfos"]:
                self._switch.update({switch["type"]: switch["enable"]})

        else:
            self._switch = {0: False}

    def _detection_sensibility(self) -> Any:
        """load detection sensibility"""
        result = "Unknown"

        if self._switch.get(DeviceSwitchType.AUTO_SLEEP.value) is not True:
            if (
                self._device["deviceInfos"]["deviceCategory"]
                == DeviceCatagories.BATTERY_CAMERA_DEVICE_CATEGORY.value
            ):
                result = self._client.get_detection_sensibility(
                    self._serial,
                    "3",
                )
            else:
                result = self._client.get_detection_sensibility(self._serial)

        if self._switch.get(DeviceSwitchType.AUTO_SLEEP.value) is True:
            result = "Hibernate"

        return result

    def _alarm_list(self) -> None:
        """get last alarm info for this camera's self._serial"""
        alarmlist = self._client.get_alarminfo(self._serial)

        if alarmlist.get("page").get("totalResults") > 0:
            self.alarmlist_time = alarmlist.get("alarms")[0].get("alarmStartTimeStr")
            self.alarmlist_pic = alarmlist.get("alarms")[0].get("picUrl")

        if self.alarmlist_time:
            self._motion_trigger(self.alarmlist_time)

    def _local_ip(self) -> str:
        """ "Fix empty ip value for certain cameras"""
        if self._device.get("wifiInfos"):
            return self._device["wifiInfos"].get("address")

        # Seems to return none or 0.0.0.0 on some. This should run 2nd.
        if self._device.get("connectionInfos"):
            if self._device["connectionInfos"].get("localIp"):
                return self._device["connectionInfos"]["localIp"]

        return "0.0.0.0"

    def _motion_trigger(self, alarmlist_time: str) -> None:
        """Create motion sensor based on last alarm time."""
        now = datetime.datetime.now().replace(microsecond=0)
        alarm_trigger_active = 0
        today_date = datetime.date.today()
        fix = datetime.datetime.now().replace(microsecond=0)

        # Need to handle error if time format different
        fix = datetime.datetime.strptime(
            alarmlist_time.replace("Today", str(today_date)),
            "%Y-%m-%d %H:%M:%S",
        )

        # returns a timedelta object
        timepassed = now - fix

        if timepassed < datetime.timedelta(seconds=60):
            alarm_trigger_active = 1

        self._alarmmotiontrigger = {
            "alarm_trigger_active": alarm_trigger_active,
            "timepassed": timepassed.total_seconds(),
        }

    def _is_alarm_schedules_enabled(self) -> bool | None:
        """Checks if alarm schedules enabled"""
        time_plans = None

        if self._device.get("timePlanInfos"):
            time_plans = [
                item for item in self._device["timePlanInfos"] if item.get("type") == 2
            ]

        if time_plans:
            return bool(time_plans[0].get("enable"))

        return None

    def status(self) -> dict[Any, Any]:
        """Return the status of the camera."""
        self.load()

        return {
            "serial": self._serial,
            "name": self._device["deviceInfos"].get("name"),
            "version": self._device["deviceInfos"].get("version"),
            "upgrade_available": self._device["statusInfos"].get("upgradeAvailable"),
            "status": self._device["deviceInfos"].get("status"),
            "device_category": self._device["deviceInfos"].get("deviceCategory"),
            "device_sub_category": self._device["deviceInfos"].get("deviceSubCategory"),
            "sleep": self._switch.get(DeviceSwitchType.SLEEP.value)
            or self._switch.get(DeviceSwitchType.AUTO_SLEEP.value),
            "privacy": self._switch.get(DeviceSwitchType.PRIVACY.value),
            "audio": self._switch.get(DeviceSwitchType.SOUND.value),
            "ir_led": self._switch.get(DeviceSwitchType.INFRARED_LIGHT.value),
            "state_led": self._switch.get(DeviceSwitchType.LIGHT.value),
            "follow_move": self._switch.get(DeviceSwitchType.MOBILE_TRACKING.value),
            "alarm_notify": bool(self._device["statusInfos"].get("globalStatus")),
            "alarm_schedules_enabled": self._is_alarm_schedules_enabled(),
            "alarm_sound_mod": SoundMode(
                self._device["statusInfos"].get("alarmSoundMode")
            ).name,
            "encrypted": bool(self._device["statusInfos"].get("isEncrypted")),
            "local_ip": self._local_ip(),
            "wan_ip": self._device.get("connectionInfos", {}).get("netIp", "0.0.0.0"),
            "local_rtsp_port": self._device["connectionInfos"].get(
                "localRtspPort", "554"
            ),
            "supported_channels": self._device["deviceInfos"].get("channelNumber"),
            "detection_sensibility": self._detection_sensibility(),
            "battery_level": self._device["statusInfos"]
            .get("optionals", {})
            .get("powerRemaining"),
            "PIR_Status": self._device["statusInfos"].get("pirStatus"),
            "Motion_Trigger": self._alarmmotiontrigger.get("alarm_trigger_active"),
            "Seconds_Last_Trigger": self._alarmmotiontrigger.get("timepassed"),
            "last_alarm_time": self.alarmlist_time,
            "last_alarm_pic": self.alarmlist_pic,
            "wifiInfos": self._device.get("wifiInfos"),
            "switches": self._switch,
        }

    def move(self, direction: str, speed: int = 5) -> bool:
        """Move camera."""
        if direction not in ["right", "left", "down", "up"]:
            raise PyEzvizError(f"Invalid direction: {direction} ")

        # launch the start command
        self._client.ptz_control(str(direction).upper(), self._serial, "START", speed)
        # launch the stop command
        self._client.ptz_control(str(direction).upper(), self._serial, "STOP", speed)

        return True

    def alarm_notify(self, enable: int) -> bool:
        """Enable/Disable camera notification when movement is detected."""
        return self._client.set_camera_defence(self._serial, enable)

    def alarm_sound(self, sound_type: int) -> bool:
        """Enable/Disable camera sound when movement is detected."""
        # we force enable = 1 , to make sound...
        return self._client.alarm_sound(self._serial, sound_type, 1)

    def alarm_detection_sensibility(self, sensibility, type_value=0):
        """Enable/Disable camera sound when movement is detected."""
        # we force enable = 1 , to make sound...
        return self._client.detection_sensibility(self._serial, sensibility, type_value)

    def switch_device_audio(self, enable=0):
        """Switch audio status on a device."""
        return self._client.switch_status(
            self._serial, DeviceSwitchType.SOUND.value, enable
        )

    def switch_device_state_led(self, enable=0):
        """Switch led status on a device."""
        return self._client.switch_status(
            self._serial, DeviceSwitchType.LIGHT.value, enable
        )

    def switch_device_ir_led(self, enable=0):
        """Switch ir status on a device."""
        return self._client.switch_status(
            self._serial, DeviceSwitchType.INFRARED_LIGHT.value, enable
        )

    def switch_privacy_mode(self, enable=0):
        """Switch privacy mode on a device."""
        return self._client.switch_status(
            self._serial, DeviceSwitchType.PRIVACY.value, enable
        )

    def switch_sleep_mode(self, enable=0):
        """Switch sleep mode on a device."""
        return self._client.switch_status(
            self._serial, DeviceSwitchType.SLEEP.value, enable
        )

    def switch_follow_move(self, enable=0):
        """Switch follow move."""
        return self._client.switch_status(
            self._serial, DeviceSwitchType.MOBILE_TRACKING.value, enable
        )

    def change_defence_schedule(self, schedule, enable=0):
        """Change defence schedule. Requires json formatted schedules."""
        return self._client.api_set_defence_schdule(self._serial, schedule, enable)
