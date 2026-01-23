import yaml


DEFAULT_CONFIG_FILE = "config.yml"


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
