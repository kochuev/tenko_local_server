import logging
import signal
import threading

from .config import Config
from .mqtt import Bridge
from .server import create_server
from .store import Store


def main():
    config = Config.from_env()
    logging.basicConfig(level=config.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    store = Store(config.state_path, config.confirmation_timeout)
    bridge = Bridge(config, store)
    server = create_server(config, store, bridge)
    stopped = threading.Event()
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda *_: stopped.set())
    bridge.start()
    worker = threading.Thread(target=server.serve_forever, name="http-server")
    worker.start()
    logging.info("HTTP listening on %s:%s; editor requires authentication", config.http_host, config.http_port)
    try:
        stopped.wait()
    finally:
        server.shutdown()
        server.server_close()
        worker.join()
        bridge.stop()
        store.close()


if __name__ == "__main__":
    main()
