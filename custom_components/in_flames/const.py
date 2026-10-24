"""Constants for the In Flames fireplace (Tuya category dbl, product dayp0pur22rp0omx)."""

DOMAIN = "in_flames"

CONF_DEVICE_ID = "device_id"
CONF_LOCAL_KEY = "local_key"

FIREPLACE_CATEGORY = "dbl"  # Tuya category for electric fireplaces
TESTED_PRODUCTS = {"dayp0pur22rp0omx"}  # product ids whose DP map below was verified on a device

# Datapoint ids. Mostly from the Tuya cloud model of this product, but the
# firmware differs from it: the cloud's countdown_set (13) is ignored and
# countdown_left (14) never moves; the working timer is the unlisted DP 103.
# Also unlisted and unused here: 16 (int, 0), 17 ("amber_and_green"),
# 25 (bool), 101 ("red"), 102 ("level_5"), 105 ("60F_16C").
DP_POWER = "1"
DP_TEMP_SET_C = "2"
DP_TEMP_CURRENT_C = "3"
DP_MODE = "4"
DP_LEVEL = "5"
DP_CHILD_LOCK = "7"
DP_LIGHT = "8"
DP_UNIT = "9"  # "c" / "f"
DP_TEMP_SET_F = "10"
DP_TEMP_CURRENT_F = "11"
DP_TIMER = "103"
DP_WORK_STATE = "15"
DP_SOUND = "20"
DP_SOUND_MODE = "21"

LEVELS = ["level_1", "level_2", "level_3", "level_4", "level_5"]
COUNTDOWNS = ["cancel", "1h", "2h", "3h", "4h", "5h", "6h"]
SOUND_MODES = ["sound_1", "sound_2", "sound_3"]

TEMP_RANGE_C = (16, 37)
TEMP_RANGE_F = (60, 99)
