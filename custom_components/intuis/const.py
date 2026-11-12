"""Constantes pour l'intégration Intuis Connect."""

from __future__ import annotations

DOMAIN = "intuis"

# Endpoints API Muller Intuitiv / Netatmo
BASE_URL = "https://app.muller-intuitiv.net"
TOKEN_URL = f"{BASE_URL}/oauth2/token"
HOMES_DATA_URL = f"{BASE_URL}/api/homesdata"
GET_MEASURE_URL = f"{BASE_URL}/api/gethomemeasure"
HOME_STATUS_URL = f"{BASE_URL}/syncapi/v1/homestatus"

# Paramètres OAuth de l'application mobile
OAUTH_CLIENT_ID = "59e604948fe283fd4dc7e355"
OAUTH_CLIENT_SECRET = "rAeWu8Y3YqXEPqRJ4BpFzFG98MRXpCcz"
OAUTH_USER_PREFIX = "muller"
OAUTH_SCOPE = "read_muller write_muller"
APP_VERSION = "1112100"

# Configuration keys
CONF_HOME_ID = "home_id"
CONF_HOME_NAME = "home_name"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_HP_START = "hp_start"
CONF_HP_END = "hp_end"
CONF_BRIDGE_MAC = "bridge_mac"

# Valeurs par défaut
DEFAULT_SCAN_INTERVAL = 30  # minutes
MIN_SCAN_INTERVAL = 10
MAX_SCAN_INTERVAL = 360

DEFAULT_HP_START = 6   # Heure de début HP (inclus)
DEFAULT_HP_END = 21    # Heure de fin HP (inclus, donc HC dès 22h ou après 21h)

# Fabricant et modèle
MANUFACTURER = "Intuis"
MODEL_RADIATOR = "Radiateur Connecté Intuis (Netatmo)"
MODEL_HUB = "Passerelle Muller Intuitiv"
