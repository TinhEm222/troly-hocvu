import logging.config
from pathlib import Path

import yaml

def setup_logging():
    project_root = Path(__file__).resolve().parent.parent
    (project_root / "logs").mkdir(parents=True, exist_ok=True)
    with (project_root / "config" / "logging.yaml").open(encoding="utf-8") as file:
        config = yaml.safe_load(file)

    # FileHandler giai quyet duong dan tu working directory. Dung duong dan tuyet
    # doi de chay on dinh qua pytest, Docker va VS Code.
    config["handlers"]["file"]["filename"] = str(project_root / "logs" / "application.log")
    logging.config.dictConfig(config)
