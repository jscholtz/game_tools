import logging
import threading
import time

from pymongo.monitoring import CommandListener

LOGGER = logging.getLogger("experiment.mongodb")
LOGGER.setLevel(logging.INFO)

READ_COMMANDS = {"aggregate", "count", "distinct", "find", "getMore", "listCollections"}
WRITE_COMMANDS = {
    "createIndexes", "delete", "drop", "dropIndexes", "findAndModify", "insert", "update",
}


class MongoTimingListener(CommandListener):
    def __init__(self):
        self._started = {}
        self._lock = threading.Lock()

    def started(self, event):
        if event.command_name not in READ_COMMANDS | WRITE_COMMANDS:
            return
        collection = event.command.get(event.command_name)
        if event.command_name == "getMore":
            collection = event.command.get("collection")
        operation = "read" if event.command_name in READ_COMMANDS else "write"
        with self._lock:
            self._started[event.request_id] = (
                operation, event.command_name, event.database_name, collection, time.perf_counter()
            )

    def succeeded(self, event):
        details = self._finish(event)
        if details is None:
            return
        operation, command, database, collection, started = details
        elapsed_ms = (time.perf_counter() - started) * 1000
        LOGGER.info(
            "MongoDB %s %s.%s command=%s succeeded duration_ms=%.2f",
            operation, database, collection or "-", command, elapsed_ms,
        )

    def failed(self, event):
        details = self._finish(event)
        if details is None:
            return
        operation, command, database, collection, started = details
        elapsed_ms = (time.perf_counter() - started) * 1000
        LOGGER.error(
            "MongoDB %s %s.%s command=%s failed duration_ms=%.2f error=%s",
            operation, database, collection or "-", command, elapsed_ms, type(event.failure).__name__,
        )

    def _finish(self, event):
        with self._lock:
            return self._started.pop(event.request_id, None)


def configure_mongo_logging():
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s")
