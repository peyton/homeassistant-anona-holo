"""Constants for the Anona Security integration."""

DOMAIN = "anona_security"

API_BASE_URL = "https://us-api.anonasecurity.com"

APP_CHANNEL = 73001001
APP_DEVICE_TYPE = 73
DEFAULT_LANG = "en_US"
PASSWORD_SIGN_SALT = "329he3wihfeibfk3209(&*^%dehsi3)*&"  # noqa: S105

DEVICE_TYPE_LOCK = 76
DEVICE_MODULE_LOCK = 76001
DEVICE_CHANNEL_LOCK = 76001001
STATUS_SMART_TYPE = 48
COMMAND_ID_UNLOCK = 6
COMMAND_ID_LOCK = 7
WEBSOCKET_COMMAND_TARGET = 2
WEBSOCKET_TIMEOUT_SECONDS = 10

ENDPOINT_GET_TS = "/baseServiceApi/V2/getTs"
ENDPOINT_LOGIN = "/accountApi/V3/userLoginPwd"
ENDPOINT_HOME_LIST = "/AnonaHomeApi/getAnonaHomeNameList"
ENDPOINT_DEVICE_LIST = "/anona/device/api/getDeviceListByHomeId"
ENDPOINT_DEVICE_INFO = "/anona/device/api/getDeviceInfo"
ENDPOINT_DEVICE_ONLINE = "/anona/device/api/getDeviceOnlineStatus"
ENDPOINT_DEVICE_STATUS = "/anona/device/status/api/getAnonaDeviceStatus"
ENDPOINT_DEVICE_CERTS = "/anona/device/api/getDeviceCertsForOwner"
ENDPOINT_WEBSOCKET_ADDRESS = "/anonaWebsocketApi/getWebsocketAddress"

CONF_EMAIL = "email"
CONF_PASSWORD = "password"  # noqa: S105
CONF_CLIENT_UUID = "client_uuid"
CONF_USER_ID = "user_id"
CONF_HOME_ID = "home_id"

UPDATE_INTERVAL_SECONDS = 30
