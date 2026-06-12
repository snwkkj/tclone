import yaml


DEFAULT_CONFIG_FILE = "config.yml"

DEFAULT_CONFIG_TEXT = """api_id:
api_hash: ""
source: -1000000000
target: -1000000000

batch_size: 100
message_delay_s: 1.0

pause_every_messages: 1000
pause_duration_s: 700
session_name: "session"
log_file: "log.log"
offset_file: "offset.json"
drop_author: true
ignore_topics: []

banner:
  enabled: true
  text: "BACKUP"
  font_file: "Roboto-Bold"
  band_color: "#9b0000"
  band_alpha: 90
  band_height_ratio: 0.22
  band_min_px: 90
  font_size_ratio: 0.74
  letter_spacing_ratio: 0.14
  letter_spacing_min_px: 4
  text_color: "#ffffff"
  outline_color: "#000000"
  outline_ratio: 0.06
  outline_min_px: 1
"""


def load_config_raw(path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_config(path):
    cfg = load_config_raw(path)

    required = ["api_id", "api_hash", "source", "target"]
    missing = [k for k in required if k not in cfg]
    if missing:
        raise ValueError(f"Missing keys in {path}: {', '.join(missing)}")

    return cfg
