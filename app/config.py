from os import getenv


def get_list(key, default=None):
    data = getenv(key, default)
    return data.split(',') if data else None


def get_int(key, default):
    return int(getenv(key, default))


def get_bool(key, default):
    return bool(getenv(key, default))


PSQL_DSN = getenv('PSQL_DSN')

OHLCV_DB_STATE = get_bool('OHLCV_DB_STATE', 'False')
OHLCV_CONFIG_FILE = getenv('OHLCV_CONFIG_FILE', 'ohlcv_config.json')

SCHEMA = getenv('SCHEMA')

MQTT_HOST = getenv('MQTT_HOST')
MQTT_PORT = get_int('MQTT_PORT', '1883')
MQTT_TOPIC_CCXT_OHLCV = getenv('MQTT_TOPIC_CCXT_OHLCV', 'ccxt/ohlcv/#')
