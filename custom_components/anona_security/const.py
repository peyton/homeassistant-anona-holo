"""Constants for the Anona-backed lock integration."""

DOMAIN = "anona_security"

API_BASE_URL = "https://us-api.anonasecurity.com"

ENDPOINT_LOGIN = "/accountApi/V3/userLoginPwd"
ENDPOINT_LOGOUT = "/accountApi/V3/userLogOut"

ENDPOINT_HOME_LIST = "/AnonaHomeApi/getAnonaHomeNameList"
ENDPOINT_HOME_INFO = "/AnonaHomeApi/getAnonaHomeInfo"
ENDPOINT_DEVICE_LIST = "/anona/device/api/getDeviceListByHomeId"
ENDPOINT_DEVICE_INFO = "/anona/device/api/getDeviceInfo"
ENDPOINT_DEVICE_ONLINE = "/anona/device/api/getDeviceOnlineStatus"

ENDPOINT_DEVICE_STATUS = "/anona/device/status/api/getAnonaDeviceStatus"
ENDPOINT_WEBSOCKET_ADDRESS = "/anonaWebsocketApi/getWebsocketAddress"

LOCK_STATE_LOCKED = 0
LOCK_STATE_UNLOCKED = 1

WS_CMD_LOCK = "lockDoor"
WS_CMD_UNLOCK = "unLockDoor"
WS_CMD_AUTH = "authSync"
WS_CMD_STATUS = "getDeviceStatus"

DEVICE_TYPE_LOCK = 76
DEVICE_MODULE_LOCK = 76001

CONF_EMAIL = "email"
CONF_PASSWORD = "password"  # noqa: S105

UPDATE_INTERVAL_SECONDS = 30

RESP_CODE = "code"
RESP_DATA = "data"
RESP_MESSAGE = "message"
RESP_SUCCESS_CODE = 0
