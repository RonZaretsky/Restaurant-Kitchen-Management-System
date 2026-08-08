import os
import re
from pathlib import Path

import yaml
from dotenv import load_dotenv

_ENV_PATTERN = re.compile(r'\$\{(\w+):\s*([^}]*)\}')

# Loaded once at import, before any config is read. Values already present in the
# real environment win, so docker-compose's env_file and an operator's shell both
# override the file. Missing .env is not an error: config.yaml still has defaults.
load_dotenv(Path(__file__).parent / ".env", override=False)


def load_config(path: Path) -> dict:
    """Read a YAML config file, substituting ${VAR: default} placeholders.

    Args:
        path: Path to the YAML file to read.

    Returns:
        The parsed config as a dict, with every placeholder replaced by the
        matching environment variable or its inline default.
    """
    content = path.read_text()
    content = _ENV_PATTERN.sub(
        lambda m: os.environ.get(m.group(1), m.group(2).strip()),
        content,
    )
    return yaml.safe_load(content)
