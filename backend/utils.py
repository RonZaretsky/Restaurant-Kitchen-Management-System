import os
import re
from pathlib import Path

import yaml

_ENV_PATTERN = re.compile(r'\$\{(\w+):\s*([^}]*)\}')


def load_config(path: Path) -> dict:
    content = path.read_text()
    content = _ENV_PATTERN.sub(
        lambda m: os.environ.get(m.group(1), m.group(2).strip()),
        content,
    )
    return yaml.safe_load(content)
