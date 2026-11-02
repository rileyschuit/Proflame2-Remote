"""Entry point: python -m proflame2d"""
import logging
import signal
import sys

from .cc1101 import Cc1101, open_spi
from .config import ConfigError, load
from .service import Service


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        config = load()
    except ConfigError as error:
        logging.error("%s", error)
        return 2
    service = Service(config, Cc1101(open_spi(config.spi_bus, config.spi_device)))
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda *_: service.stop())
    service.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
