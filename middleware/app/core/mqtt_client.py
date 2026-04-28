import asyncio
import json
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Callable, Dict, Any, Coroutine

from aiomqtt import Client

from app.core.config import settings


class MQTTClient:
    def __init__(self):
        self._logger = self._create_logger()
        self.message_handlers: Dict[str, Callable[[str, bytes], Coroutine[Any, Any, None]]] = {}
        self._task: asyncio.Task | None = None
        self._connected = False
        self._publish_queue: asyncio.Queue = asyncio.Queue()
        self._publish_task: asyncio.Task | None = None

    def _create_logger(self) -> logging.Logger:
        logger = logging.getLogger("mqtt_client")
        if logger.handlers:
            return logger

        logger.setLevel(logging.DEBUG)

        app_dir = Path(__file__).resolve().parent.parent
        log_dir = app_dir / "log"
        log_dir.mkdir(parents=True, exist_ok=True)

        fmt = logging.Formatter(
            fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        file_handler = RotatingFileHandler(
            log_dir / "mqtt_client.log",
            maxBytes=50 * 1024 * 1024,
            backupCount=10,
            encoding="utf-8",
        )
        try:
            os.chmod(log_dir / "mqtt_client.log", 0o666)
        except OSError:
            pass
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(fmt)

        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(logging.INFO)
        stream_handler.setFormatter(fmt)

        logger.addHandler(file_handler)
        logger.addHandler(stream_handler)
        logger.propagate = False
        return logger

    def _new_client(self) -> Client:
        return Client(
            hostname=settings.MQTT_HOST,
            port=settings.MQTT_PORT,
            username=settings.MQTT_USERNAME,
            password=settings.MQTT_PASSWORD,
            keepalive=60,
        )

    async def connect(self):
        try:
            self._connected = True
            self._task = asyncio.create_task(self._message_loop())
            self._publish_task = asyncio.create_task(self._publish_loop())
            self._logger.info(
                "MQTT client created host=%s port=%s username=%s",
                settings.MQTT_HOST,
                settings.MQTT_PORT,
                settings.MQTT_USERNAME,
            )
        except Exception as e:
            self._logger.exception("MQTT connection error: %s", e)
            raise

    async def disconnect(self):
        if self._publish_task:
            self._publish_task.cancel()
            try:
                await self._publish_task
            except asyncio.CancelledError:
                pass
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._connected = False
        self._logger.info("MQTT disconnected")

    def subscribe(self, topic: str, handler: Callable[[str, bytes], Coroutine[Any, Any, None]]):
        self.message_handlers[topic] = handler
        self._logger.info("Registered handler for topic=%s", topic)

    async def publish(self, topic: str, payload: str | bytes, qos: int = 0):
        await self._publish_queue.put((topic, payload, qos))

    async def _publish_loop(self):
        while self._connected:
            try:
                topic, payload, qos = await asyncio.wait_for(self._publish_queue.get(), timeout=1.0)
                async with self._new_client() as client:
                    await client.publish(topic, payload, qos=qos)
                    self._logger.debug("Published topic=%s qos=%s payload=%s", topic, qos, payload)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                self._logger.exception("Publish error: %s", e)

    async def _message_loop(self):
        while self._connected:
            try:
                async with self._new_client() as client:
                    for topic in self.message_handlers.keys():
                        await client.subscribe(topic)
                        self._logger.info("Subscribed topic=%s", topic)

                    async for message in client.messages:
                        await self._handle_message(message)
            except Exception as e:
                self._logger.exception("MQTT message loop error: %s", e)
                await asyncio.sleep(1)

    async def _handle_message(self, message):
        topic = str(message.topic)
        payload = message.payload
        self._logger.debug("Received topic=%s payload=%s", topic, payload)

        for pattern, handler in self.message_handlers.items():
            if self._topic_match(pattern, topic):
                try:
                    await handler(topic, payload)
                except Exception as e:
                    self._logger.exception("Error handling message topic=%s: %s", topic, e)

    def _topic_match(self, pattern: str, topic: str) -> bool:
        pattern_parts = pattern.split('/')
        topic_parts = topic.split('/')

        if len(pattern_parts) != len(topic_parts):
            return False

        for p, t in zip(pattern_parts, topic_parts):
            if p == '#':
                return True
            if p == '+':
                continue
            if p != t:
                return False

        return True


mqtt_client = MQTTClient()
