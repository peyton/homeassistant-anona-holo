"""Create a default Home Assistant config for local development."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

DEFAULT_CONFIGURATION_YAML = """\
# https://www.home-assistant.io/integrations/default_config/
frontend:
history:
logbook:
sun:
system_health:

# https://www.home-assistant.io/integrations/homeassistant/
homeassistant:
    debug: true

http:
    use_x_forwarded_for: true
    trusted_proxies:
        - FC00::/7

# https://www.home-assistant.io/integrations/logger/
logger:
    default: info
    logs:
        custom_components.anona_security: debug
"""


def ensure_dev_config(config_dir: Path) -> Path:
    """Create the default local Home Assistant config if it is missing."""
    config_dir.mkdir(parents=True, exist_ok=True)
    configuration_path = config_dir / "configuration.yaml"
    if not configuration_path.exists():
        configuration_path.write_text(DEFAULT_CONFIGURATION_YAML)
    return configuration_path


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    """Parse CLI arguments for the config bootstrap helper."""
    parser = argparse.ArgumentParser(
        description="Create the default Home Assistant development config."
    )
    parser.add_argument(
        "--config-dir",
        type=Path,
        default=Path("config"),
        help="Path to the Home Assistant config directory.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the config bootstrap helper."""
    args = _parse_args(argv)
    ensure_dev_config(args.config_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
