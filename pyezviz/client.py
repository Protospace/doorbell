"""Ezviz API."""
from __future__ import annotations

import hashlib
import logging
from typing import Any
from uuid import uuid4

import requests

from pyezviz.camera import EzvizCamera
from pyezviz.cas import EzvizCAS
from pyezviz.constants import (
    DEFAULT_TIMEOUT,
    FEATURE_CODE,
    MAX_RETRIES,
    DefenseModeType,
    DeviceCatagories,
)
from pyezviz.exceptions import HTTPError, InvalidURL, PyEzvizError

API_ENDPOINT_CLOUDDEVICES = "/api/cloud/v2/cloudDevices/getAll"
API_ENDPOINT_PAGELIST = "/v3/userdevices/v1/devices/pagelist"
API_ENDPOINT_DEVICES = "/v3/devices/"
API_ENDPOINT_LOGIN = "/v3/users/login/v5"
API_ENDPOINT_REFRESH_SESSION_ID = "/v3/apigateway/login"
API_ENDPOINT_SWITCH_STATUS = "/switchStatus"
API_ENDPOINT_PTZCONTROL = "/ptzControl"
API_ENDPOINT_ALARM_SOUND = "/alarm/sound"
API_ENDPOINT_DETECTION_SENSIBILITY = "/api/device/configAlgorithm"
API_ENDPOINT_DETECTION_SENSIBILITY_GET = "/api/device/queryAlgorithmConfig"
API_ENDPOINT_ALARMINFO_GET = "/v3/alarms/v2/advanced"
API_ENDPOINT_SET_DEFENCE_SCHEDULE = "/api/device/defence/plan2"
API_ENDPOINT_SWITCH_DEFENCE_MODE = "/v3/userdevices/v1/group/switchDefenceMode"
API_ENDPOINT_SWITCH_SOUND_ALARM = "/sendAlarm"
API_ENDPOINT_SERVER_INFO = "/v3/configurations/system/info"


class EzvizClient:
    """Initialize api client object."""

    def __init__(
        self,
        account: str | None = None,
        password: str | None = None,
        url: str = "apiieu.ezvizlife.com",
        timeout: int = DEFAULT_TIMEOUT,
        token: dict | None = None,
    ) -> None:
        """Initialize the client object."""
        self.account = account
        self.password = password
        self._session = requests.session()
        # Set Android generic user agent.
        self._session.headers.update({"User-Agent": "okhttp/3.12.1"})
        self._token = token or {
            "session_id": None,
            "rf_session_id": None,
            "username": None,
            "api_url": url,
        }
        self._timeout = timeout

    def _login(self, account: str, password: str) -> dict[Any, Any]:
        """Login to Ezviz API."""

        # Region code to url.
        if len(self._token["api_url"].split(".")) == 1:
            self._token["api_url"] = "apii" + self._token["api_url"] + ".ezvizlife.com"

        # Ezviz API sends md5 of password
        temp = hashlib.md5()
        temp.update(password.encode("utf-8"))
        md5pass = temp.hexdigest()
        payload = {
            "account": account,
            "password": md5pass,
            "featureCode": FEATURE_CODE,
            "msgType": "0",
            "cuName": "SFRDIDEw",
        }

        try:
            req = self._session.post(
                "https://" + self._token["api_url"] + API_ENDPOINT_LOGIN,
                allow_redirects=False,
                headers={
                    "clientType": "3",
                    "customno": "1000001",
                    "clientNo": "web_site",
                    "appId": "ys7",
                    "lang": "en",
                },
                data=payload,
                timeout=self._timeout,
            )

            req.raise_for_status()

        except requests.ConnectionError as err:
            raise InvalidURL("A Invalid URL or Proxy error occured") from err

        except requests.HTTPError as err:
            raise HTTPError from err

        try:
            json_result = req.json()

        except ValueError as err:
            raise PyEzvizError(
                "Impossible to decode response: "
                + str(err)
                + "\nResponse was: "
                + str(req.text)
            ) from err

        if json_result["meta"]["code"] == 1100:
            self._token["api_url"] = json_result["loginArea"]["apiDomain"]
            print("Region incorrect!")
            print(f"Your region url: {self._token['api_url']}")
            self.close_session()
            return self.login()

        if json_result["meta"]["code"] == 1013:
            raise PyEzvizError("Incorrect Username.")

        if json_result["meta"]["code"] == 1014:
            raise PyEzvizError("Incorrect Password.")

        if json_result["meta"]["code"] == 1015:
            raise PyEzvizError("The user is locked.")

        self._token["session_id"] = str(json_result["loginSession"]["sessionId"])
        self._token["rf_session_id"] = str(json_result["loginSession"]["rfSessionId"])
        self._token["username"] = str(json_result["loginUser"]["username"])
        self._token["api_url"] = str(json_result["loginArea"]["apiDomain"])
        if not self._token["session_id"]:
            raise PyEzvizError(
                f"Login error: Please check your username/password: {req.text}"
            )

        self._token["service_urls"] = self.get_service_urls()

        return self._token

    def get_service_urls(self) -> Any:
        """Get Ezviz service urls."""

        try:
            req = self._session.get(
                f"https://{self._token['api_url']}{API_ENDPOINT_SERVER_INFO}",
                headers={
                    "sessionId": self._token["session_id"],
                    "featureCode": FEATURE_CODE,
                },
                timeout=self._timeout,
            )

            req.raise_for_status()

        except requests.ConnectionError as err:
            raise InvalidURL("A Invalid URL or Proxy error occured") from err

        except requests.HTTPError as err:
            if err.response.status_code == 401:
                # session is wrong, need to relogin
                self.login()

            raise HTTPError from err

        if not req.text:
            raise PyEzvizError("No data")

        try:
            json_output = req.json()

        except ValueError as err:
            raise PyEzvizError(
                "Impossible to decode response: "
                + str(err)
                + "\nResponse was: "
                + str(req.text)
            ) from err

        if json_output.get("meta").get("code") != 200:
            logging.info("Json request error")

        service_urls = json_output["systemConfigInfo"]
        service_urls["sysConf"] = service_urls["sysConf"].split("|")

        return service_urls

    def _api_get_pagelist(
        self, page_filter: str, json_key: str | None = None, max_retries: int = 0
    ) -> Any:
        """Get data from pagelist API."""

        if max_retries > MAX_RETRIES:
            raise PyEzvizError("Can't gather proper data. Max retries exceeded.")

        if page_filter is None:
            raise PyEzvizError("Trying to call get_pagelist without filter")

        try:
            req = self._session.get(
                "https://" + self._token["api_url"] + API_ENDPOINT_PAGELIST,
                headers={"sessionId": self._token["session_id"]},
                params={"filter": page_filter},
                timeout=self._timeout,
            )

            req.raise_for_status()

        except requests.HTTPError as err:
            if err.response.status_code == 401:
                # session is wrong, need to relogin
                self.login()
                return self._api_get_pagelist(page_filter, json_key, max_retries + 1)

            raise HTTPError from err

        if not req.text:
            raise PyEzvizError("No data")

        try:
            json_output = req.json()

        except ValueError as err:
            raise PyEzvizError(
                "Impossible to decode response: "
                + str(err)
                + "\nResponse was: "
                + str(req.text)
            ) from err

        if json_output.get("meta").get("code") != 200:
            # session is wrong, need to relogin
            self.login()
            logging.info(
                "Json request error, relogging (max retries: %s)", str(max_retries)
            )
            return self._api_get_pagelist(page_filter, json_key, max_retries + 1)

        if json_key is None:
            json_result = json_output
        else:
            json_result = json_output[json_key]

        if not json_result:
            # session is wrong, need to relogin
            self.login()
            logging.info(
                "Impossible to load the devices, here is the returned response: %s",
                str(req.text),
            )
            return self._api_get_pagelist(page_filter, json_key, max_retries + 1)

        return json_result

    def get_alarminfo(self, serial: str, max_retries: int = 0) -> Any:
        """Get data from alarm info API."""
        if max_retries > MAX_RETRIES:
            raise PyEzvizError("Can't gather proper data. Max retries exceeded.")

        params: dict[str, int | str] = {
            "deviceSerials": serial,
            "queryType": -1,
            "limit": 1,
            "stype": -1,
        }

        try:
            req = self._session.get(
                "https://" + self._token["api_url"] + API_ENDPOINT_ALARMINFO_GET,
                headers={"sessionId": self._token["session_id"]},
                params=params,
                timeout=self._timeout,
            )

            req.raise_for_status()

        except requests.HTTPError as err:
            if err.response.status_code == 401:
                # session is wrong, need to relogin
                self.login()
                return self.get_alarminfo(serial, max_retries + 1)

            raise HTTPError from err

        if req.text == "":
            raise PyEzvizError("No data")

        try:
            json_output = req.json()

        except ValueError as err:
            raise PyEzvizError(
                "Impossible to decode response: "
                + str(err)
                + "\nResponse was: "
                + str(req.text)
            ) from err

        return json_output

    def _switch_status(
        self, serial: str, status_type: int, enable: int, max_retries: int = 0
    ) -> bool:
        """Switch status on a device."""
        if max_retries > MAX_RETRIES:
            raise PyEzvizError("Can't gather proper data. Max retries exceeded.")

        try:
            req = self._session.put(
                "https://"
                + self._token["api_url"]
                + API_ENDPOINT_DEVICES
                + serial
                + "/1/1/"
                + str(status_type)
                + API_ENDPOINT_SWITCH_STATUS,
                headers={"sessionId": self._token["session_id"]},
                data={
                    "enable": enable,
                    "serial": serial,
                    "channelNo": "1",
                    "type": status_type,
                },
                timeout=self._timeout,
            )

            req.raise_for_status()

        except requests.HTTPError as err:
            if err.response.status_code == 401:
                # session is wrong, need to relogin
                self.login()
                return self._switch_status(serial, status_type, enable, max_retries + 1)

            raise HTTPError from err

        try:
            json_output = req.json()

        except ValueError as err:
            raise PyEzvizError(
                "Impossible to decode response: "
                + str(err)
                + "\nResponse was: "
                + str(req.text)
            ) from err

        if json_output.get("meta").get("code") != 200:
            raise PyEzvizError(
                f"Could not set the switch: Got {req.status_code} : {req.text})"
            )

        return True

    def sound_alarm(self, serial: str, enable: int = 1, max_retries: int = 0) -> bool:
        """Sound alarm on a device."""
        if max_retries > MAX_RETRIES:
            raise PyEzvizError("Can't gather proper data. Max retries exceeded.")

        try:
            req = self._session.put(
                "https://"
                + self._token["api_url"]
                + API_ENDPOINT_DEVICES
                + serial
                + "/0"
                + API_ENDPOINT_SWITCH_SOUND_ALARM,
                headers={"sessionId": self._token["session_id"]},
                data={
                    "enable": enable,
                },
                timeout=self._timeout,
            )

            req.raise_for_status()

        except requests.HTTPError as err:
            if err.response.status_code == 401:
                # session is wrong, need to relogin
                self.login()
                return self.sound_alarm(serial, enable, max_retries + 1)

            raise HTTPError from err

        try:
            json_output = req.json()

        except ValueError as err:
            raise PyEzvizError(
                "Impossible to decode response: "
                + str(err)
                + "\nResponse was: "
                + str(req.text)
            ) from err

        if json_output.get("meta").get("code") != 200:
            raise PyEzvizError(
                f"Could not set the alarm sound: Got {req.status_code} : {req.text})"
            )

        return True

    def load_cameras(self) -> dict[Any, Any]:
        """Load and return all cameras objects."""

        devices = self._get_all_device_infos()
        cameras = {}
        supported_categories = [
            DeviceCatagories.COMMON_DEVICE_CATEGORY.value,
            DeviceCatagories.CAMERA_DEVICE_CATEGORY.value,
            DeviceCatagories.BATTERY_CAMERA_DEVICE_CATEGORY.value,
            DeviceCatagories.DOORBELL_DEVICE_CATEGORY.value,
            DeviceCatagories.BASE_STATION_DEVICE_CATEGORY.value,
        ]

        for device, data in devices.items():
            if data["deviceInfos"]["deviceCategory"] in supported_categories:
                # Add support for connected HikVision cameras
                if (
                    data["deviceInfos"]["deviceCategory"]
                    == DeviceCatagories.COMMON_DEVICE_CATEGORY.value
                    and not data["deviceInfos"]["hik"]
                ):
                    continue

                # Create camera object

                camera = EzvizCamera(self, device, data)

                camera.load()
                cameras[device] = camera.status()

        return cameras

    def _get_all_device_infos(self) -> dict[Any, Any]:
        """Load all devices and build dict per device serial."""

        devices = self._get_page_list()
        result: dict[Any, Any] = {}

        for device in devices["deviceInfos"]:
            result[device["deviceSerial"]] = {}
            result[device["deviceSerial"]]["deviceInfos"] = device
            result[device["deviceSerial"]]["connectionInfos"] = devices.get(
                "connectionInfos"
            ).get(device["deviceSerial"])
            result[device["deviceSerial"]]["p2pInfos"] = devices.get("p2pInfos").get(
                device["deviceSerial"]
            )
            result[device["deviceSerial"]]["alarmNodisturbInfos"] = devices.get(
                "alarmNodisturbInfos"
            ).get(device["deviceSerial"])
            result[device["deviceSerial"]]["kmsInfos"] = devices.get("kmsInfos").get(
                device["deviceSerial"]
            )
            result[device["deviceSerial"]]["timePlanInfos"] = devices.get(
                "timePlanInfos"
            ).get(device["deviceSerial"])
            result[device["deviceSerial"]]["statusInfos"] = devices.get(
                "statusInfos"
            ).get(device["deviceSerial"])
            result[device["deviceSerial"]]["wifiInfos"] = devices.get("wifiInfos").get(
                device["deviceSerial"]
            )
            result[device["deviceSerial"]]["switchStatusInfos"] = devices.get(
                "switchStatusInfos"
            ).get(device["deviceSerial"])
            for item in devices["cameraInfos"]:
                if item["deviceSerial"] == device["deviceSerial"]:
                    result[device["deviceSerial"]]["cameraInfos"] = item

        return result

    def get_all_per_serial_infos(self, serial: str) -> dict[Any, Any] | None:
        """Load all devices and build dict per device serial."""

        if serial is None:
            raise PyEzvizError("Need serial number for this query")

        devices = self._get_page_list()
        result: dict[str, dict] = {serial: {}}

        for device in devices["deviceInfos"]:
            if device["deviceSerial"] == serial:
                result[device["deviceSerial"]]["deviceInfos"] = device
                result[device["deviceSerial"]]["deviceInfos"] = device
                result[device["deviceSerial"]]["connectionInfos"] = devices.get(
                    "connectionInfos"
                ).get(device["deviceSerial"])
                result[device["deviceSerial"]]["p2pInfos"] = devices.get(
                    "p2pInfos"
                ).get(device["deviceSerial"])
                result[device["deviceSerial"]]["alarmNodisturbInfos"] = devices.get(
                    "alarmNodisturbInfos"
                ).get(device["deviceSerial"])
                result[device["deviceSerial"]]["kmsInfos"] = devices.get(
                    "kmsInfos"
                ).get(device["deviceSerial"])
                result[device["deviceSerial"]]["timePlanInfos"] = devices.get(
                    "timePlanInfos"
                ).get(device["deviceSerial"])
                result[device["deviceSerial"]]["statusInfos"] = devices.get(
                    "statusInfos"
                ).get(device["deviceSerial"])
                result[device["deviceSerial"]]["wifiInfos"] = devices.get(
                    "wifiInfos"
                ).get(device["deviceSerial"])
                result[device["deviceSerial"]]["switchStatusInfos"] = devices.get(
                    "switchStatusInfos"
                ).get(device["deviceSerial"])
                for item in devices["cameraInfos"]:
                    if item["deviceSerial"] == device["deviceSerial"]:
                        result[device["deviceSerial"]]["cameraInfos"] = item

        return result.get(serial)

    def ptz_control(
        self, command: str, serial: str, action: str, speed: int = 5
    ) -> Any:
        """PTZ Control by API."""
        if command is None:
            raise PyEzvizError("Trying to call ptzControl without command")
        if action is None:
            raise PyEzvizError("Trying to call ptzControl without action")

        try:
            req = self._session.put(
                "https://"
                + self._token["api_url"]
                + API_ENDPOINT_DEVICES
                + serial
                + API_ENDPOINT_PTZCONTROL,
                data={
                    "command": command,
                    "action": action,
                    "channelNo": "1",
                    "speed": speed,
                    "uuid": str(uuid4()),
                    "serial": serial,
                },
                headers={"sessionId": self._token["session_id"], "clientType": "1"},
                timeout=self._timeout,
            )

            req.raise_for_status()

        except requests.HTTPError as err:
            raise HTTPError from err

        return req.text

    def login(self) -> dict[Any, Any]:
        """Get or refresh ezviz login token."""
        if self._token["session_id"] and self._token["rf_session_id"]:
            try:
                req = self._session.put(
                    "https://"
                    + self._token["api_url"]
                    + API_ENDPOINT_REFRESH_SESSION_ID,
                    data={
                        "refreshSessionId": self._token["rf_session_id"],
                        "featureCode": FEATURE_CODE,
                    },
                    headers={"sessionId": self._token["session_id"]},
                    timeout=self._timeout,
                )
                req.raise_for_status()

            except requests.HTTPError as err:
                raise HTTPError from err

            try:
                json_result = req.json()

            except ValueError as err:
                raise PyEzvizError(
                    "Impossible to decode response: "
                    + str(err)
                    + "\nResponse was: "
                    + str(req.text)
                ) from err

            self._token["session_id"] = str(json_result["sessionInfo"]["sessionId"])
            self._token["rf_session_id"] = str(
                json_result["sessionInfo"]["refreshSessionId"]
            )
            if not self._token["session_id"]:
                raise PyEzvizError(f"Relogin required: {req.text}")

            if not self._token.get("service_urls"):
                self._token["service_urls"] = self.get_service_urls()

            return self._token

        if self.account and self.password:
            return self._login(account=self.account, password=self.password)

        raise PyEzvizError("Login with account and password required")

    def set_camera_defence(self, serial: str, enable: int) -> bool:
        """Enable/Disable motion detection on camera."""
        cas_client = EzvizCAS(self._token)
        cas_client.set_camera_defence_state(serial, enable)

        return True

    def api_set_defence_schedule(
        self, serial: str, schedule: str, enable: int, max_retries: int = 0
    ) -> bool:
        """Set defence schedules."""
        if max_retries > MAX_RETRIES:
            raise PyEzvizError("Can't gather proper data. Max retries exceeded.")

        schedulestring = (
            '{"CN":0,"EL":'
            + str(enable)
            + ',"SS":"'
            + serial
            + '","WP":['
            + schedule
            + "]}]}"
        )
        try:
            req = self._session.post(
                "https://" + self._token["api_url"] + API_ENDPOINT_SET_DEFENCE_SCHEDULE,
                headers={"sessionId": self._token["session_id"]},
                data={
                    "devTimingPlan": schedulestring,
                },
                timeout=self._timeout,
            )

            req.raise_for_status()

        except requests.HTTPError as err:
            if err.response.status_code == 401:
                # session is wrong, need to relogin
                self.login()
                return self.api_set_defence_schedule(
                    serial, schedule, enable, max_retries + 1
                )

            raise HTTPError from err

        try:
            json_output = req.json()

        except ValueError as err:
            raise PyEzvizError(
                "Impossible to decode response: "
                + str(err)
                + "\nResponse was: "
                + str(req.text)
            ) from err

        if json_output.get("resultCode") != 0:
            raise PyEzvizError(
                f"Could not set the schedule: Got {req.status_code} : {req.text})"
            )

        return True

    def api_set_defence_mode(self, mode: DefenseModeType, max_retries: int = 0) -> bool:
        """Set defence mode."""
        if max_retries > MAX_RETRIES:
            raise PyEzvizError("Can't gather proper data. Max retries exceeded.")

        try:
            req = self._session.post(
                "https://" + self._token["api_url"] + API_ENDPOINT_SWITCH_DEFENCE_MODE,
                headers={"sessionId": self._token["session_id"]},
                data={
                    "groupId": -1,
                    "mode": mode,
                },
                timeout=self._timeout,
            )

            req.raise_for_status()

        except requests.HTTPError as err:
            if err.response.status_code == 401:
                # session is wrong, need to relogin
                self.login()
                return self.api_set_defence_mode(mode, max_retries + 1)

            raise HTTPError from err

        try:
            json_output = req.json()

        except ValueError as err:
            raise PyEzvizError(
                "Impossible to decode response: "
                + str(err)
                + "\nResponse was: "
                + str(req.text)
            ) from err

        if json_output.get("meta").get("code") != 200:
            raise PyEzvizError(
                f"Could not set defence mode: Got {req.status_code} : {req.text})"
            )

        return True

    def detection_sensibility(
        self,
        serial: str,
        sensibility: int = 3,
        type_value: int = 3,
        max_retries: int = 0,
    ) -> bool | str:
        """Set detection sensibility."""
        if max_retries > MAX_RETRIES:
            raise PyEzvizError("Can't gather proper data. Max retries exceeded.")

        if sensibility not in [0, 1, 2, 3, 4, 5, 6] and type_value == 0:
            raise PyEzvizError(
                "Unproper sensibility for type 0 (should be within 1 to 6)."
            )

        try:
            req = self._session.post(
                "https://"
                + self._token["api_url"]
                + API_ENDPOINT_DETECTION_SENSIBILITY,
                headers={"sessionId": self._token["session_id"]},
                data={
                    "subSerial": serial,
                    "type": type_value,
                    "channelNo": "1",
                    "value": sensibility,
                },
                timeout=self._timeout,
            )

            req.raise_for_status()

        except requests.HTTPError as err:
            if err.response.status_code == 401:
                # session is wrong, need to re-log-in
                self.login()
                return self.detection_sensibility(
                    serial, sensibility, type_value, max_retries + 1
                )

            raise HTTPError from err

        try:
            response_json = req.json()

        except ValueError as err:
            raise PyEzvizError("Could not decode response:" + str(err)) from err

        if response_json["resultCode"] and response_json["resultCode"] != "0":
            return "Unknown value"

        return True

    def get_detection_sensibility(
        self, serial: str, type_value: str = "0", max_retries: int = 0
    ) -> Any:
        """Get detection sensibility notifications."""
        if max_retries > MAX_RETRIES:
            raise PyEzvizError("Can't gather proper data. Max retries exceeded.")

        try:
            req = self._session.post(
                "https://"
                + self._token["api_url"]
                + API_ENDPOINT_DETECTION_SENSIBILITY_GET,
                headers={"sessionId": self._token["session_id"]},
                data={
                    "subSerial": serial,
                },
                timeout=self._timeout,
            )

            req.raise_for_status()

        except requests.HTTPError as err:
            if err.response.status_code == 401:
                # session is wrong, need to re-log-in.
                self.login()
                return self.get_detection_sensibility(
                    serial, type_value, max_retries + 1
                )

            raise HTTPError from err

        try:
            response_json = req.json()

        except ValueError as err:
            raise PyEzvizError("Could not decode response:" + str(err)) from err

        if response_json["resultCode"] != "0":
            return "Unknown"

        if response_json["algorithmConfig"]["algorithmList"]:
            for idx in response_json["algorithmConfig"]["algorithmList"]:
                if idx["type"] == type_value:
                    return idx["value"]

        return "Unknown"

    # soundtype: 0 = normal, 1 = intensive, 2 = disabled ... don't ask me why...
    def alarm_sound(
        self, serial: str, sound_type: int, enable: int = 1, max_retries: int = 0
    ) -> bool:
        """Enable alarm sound by API."""
        if max_retries > MAX_RETRIES:
            raise PyEzvizError("Can't gather proper data. Max retries exceeded.")

        if sound_type not in [0, 1, 2]:
            raise PyEzvizError(
                "Invalid sound_type, should be 0,1,2: " + str(sound_type)
            )

        try:
            req = self._session.put(
                "https://"
                + self._token["api_url"]
                + API_ENDPOINT_DEVICES
                + serial
                + API_ENDPOINT_ALARM_SOUND,
                headers={"sessionId": self._token["session_id"]},
                data={
                    "enable": enable,
                    "soundType": sound_type,
                    "voiceId": "0",
                    "deviceSerial": serial,
                },
                timeout=self._timeout,
            )

            req.raise_for_status()

        except requests.HTTPError as err:
            if err.response.status_code == 401:
                # session is wrong, need to re-log-in
                self.login()
                return self.alarm_sound(serial, sound_type, enable, max_retries + 1)

            raise HTTPError from err

        return True

    def switch_status(self, serial: str, status_type: int, enable: int = 0) -> bool:
        """Switch status of a device."""
        return self._switch_status(serial, status_type, enable)

    def _get_page_list(self) -> Any:
        """Get ezviz device info broken down in sections."""
        return self._api_get_pagelist(
            page_filter="CLOUD, TIME_PLAN, CONNECTION, SWITCH,"
            "STATUS, WIFI, NODISTURB, KMS, P2P,"
            "TIME_PLAN, CHANNEL, VTM, DETECTOR,"
            "FEATURE, UPGRADE, VIDEO_QUALITY, QOS",
            json_key=None,
        )

    def get_device(self) -> Any:
        """Get ezviz devices filter."""
        return self._api_get_pagelist(page_filter="CLOUD", json_key="deviceInfos")

    def get_connection(self) -> Any:
        """Get ezviz connection infos filter."""
        return self._api_get_pagelist(
            page_filter="CONNECTION", json_key="connectionInfos"
        )

    def _get_status(self) -> Any:
        """Get ezviz status infos filter."""
        return self._api_get_pagelist(page_filter="STATUS", json_key="statusInfos")

    def get_switch(self) -> Any:
        """Get ezviz switch infos filter."""
        return self._api_get_pagelist(
            page_filter="SWITCH", json_key="switchStatusInfos"
        )

    def _get_wifi(self) -> Any:
        """Get ezviz wifi infos filter."""
        return self._api_get_pagelist(page_filter="WIFI", json_key="wifiInfos")

    def _get_nodisturb(self) -> Any:
        """Get ezviz nodisturb infos filter."""
        return self._api_get_pagelist(
            page_filter="NODISTURB", json_key="alarmNodisturbInfos"
        )

    def _get_p2p(self) -> Any:
        """Get ezviz P2P infos filter."""
        return self._api_get_pagelist(page_filter="P2P", json_key="p2pInfos")

    def _get_kms(self) -> Any:
        """Get ezviz KMS infos filter."""
        return self._api_get_pagelist(page_filter="KMS", json_key="kmsInfos")

    def _get_time_plan(self) -> Any:
        """Get ezviz TIME_PLAN infos filter."""
        return self._api_get_pagelist(page_filter="TIME_PLAN", json_key="timePlanInfos")

    def close_session(self) -> None:
        """Clear current session."""
        if self._session:
            self._session.close()

        self._session = requests.session()
        self._session.headers.update(
            {"User-Agent": "okhttp/3.12.1"}
        )  # Android generic user agent.
