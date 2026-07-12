"""config/court-spec.v1.yaml, config/segmentation.v1.yaml, config/precheck.v1.yaml のロード。

しきい値・コート寸法をコードにハードコードしない（CLAUDE.md 不変原則2）。
CONFIG_DIR 環境変数でリポジトリの config/ を指す（docker-composeでマウント）。
"""

import os
from functools import lru_cache
from pathlib import Path

import yaml

CONFIG_DIR = Path(os.environ.get("CONFIG_DIR", "/app/config"))


@lru_cache
def load_court_spec(version: str = "v1") -> dict:
    path = CONFIG_DIR / f"court-spec.{version}.yaml"
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache
def load_segmentation_params(version: str = "v1") -> dict:
    path = CONFIG_DIR / f"segmentation.{version}.yaml"
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache
def load_precheck_params(version: str = "v1") -> dict:
    path = CONFIG_DIR / f"precheck.{version}.yaml"
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache
def load_shot_mechanics(version: str = "v1") -> dict:
    path = CONFIG_DIR / f"shot-mechanics.{version}.yaml"
    with open(path, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    from cvpipeline.pose.config_validation import validate_shot_mechanics

    validate_shot_mechanics(config)
    return config
