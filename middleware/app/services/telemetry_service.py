import json
from datetime import datetime
from typing import Dict, Any, Optional

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import SessionLocal
from app.core.redis import redis_client


class TelemetryService:
    """
    遥测数据服务类
    负责处理设备遥测数据和事件的接收、存储和查询
    数据流向：MQTT -> Redis 缓存 -> MySQL 持久化
    """

    @staticmethod
    async def process_telemetry(topic: str, payload: bytes):
        """
        处理接收到的 MQTT 遥测数据

        Args:
            topic: MQTT 主题，格式为 telemetry/plc/{device_id}
            payload: 遥测数据（JSON 格式）

        处理流程：
        1. 解析 MQTT 主题获取设备ID
        2. 解析遥测数据
        3. 将数据存入 Redis（TTL 300 秒）
        4. 将数据持久化到 MySQL 数据库
        """
        try:
            # 尝试解析 JSON 格式的遥测数据
            data = json.loads(payload.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError):
            # 解析失败时，保存原始数据
            data = {"raw": payload.decode('utf-8', errors='ignore')}

        # 解析 MQTT 主题，提取设备ID
        # 主题格式: telemetry/plc/{device_id}
        parts = topic.split('/')
        if len(parts) >= 3 and parts[0] == 'telemetry' and parts[1] == 'plc':
            device_id = parts[2] if len(parts) > 2 else 'unknown'

            # 构建遥测数据结构
            telemetry_data = {
                'device_id': device_id,
                'timestamp': datetime.utcnow().isoformat(),
                'data': data
            }

            # 将最新遥测数据存入 Redis，TTL 300 秒（5分钟）
            await redis_client.setex(
                f"telemetry:{device_id}",
                300,
                json.dumps(telemetry_data)
            )

            # 将遥测数据持久化到数据库
            async with SessionLocal() as db:
                await TelemetryService._save_to_db(db, device_id, telemetry_data)

    @staticmethod
    async def process_event(topic: str, payload: bytes):
        """
        处理接收到的 MQTT 设备事件

        Args:
            topic: MQTT 主题，格式为 event/plc/{device_id}
            payload: 事件数据（JSON 格式）

        处理流程：
        1. 解析 MQTT 主题获取设备ID
        2. 解析事件数据
        3. 将最新事件存入 Redis（TTL 3600 秒）
        4. 将事件添加到历史记录列表（保留最近 100 条）
        """
        try:
            # 尝试解析 JSON 格式的事件数据
            data = json.loads(payload.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError):
            # 解析失败时，保存原始数据
            data = {"raw": payload.decode('utf-8', errors='ignore')}

        # 解析 MQTT 主题，提取设备ID
        # 主题格式: event/plc/{device_id}
        parts = topic.split('/')
        if len(parts) >= 3 and parts[0] == 'event' and parts[1] == 'plc':
            device_id = parts[2] if len(parts) > 2 else 'unknown'

            # 构建事件数据结构
            event_data = {
                'device_id': device_id,
                'timestamp': datetime.utcnow().isoformat(),
                'event': data
            }

            # 将最新事件存入 Redis，TTL 3600 秒（1小时）
            await redis_client.setex(
                f"event:{device_id}",
                3600,
                json.dumps(event_data)
            )

            # 将事件添加到历史记录列表（List），保留最近 100 条
            await redis_client.lpush(
                f"events:{device_id}",
                json.dumps(event_data)
            )
            await redis_client.ltrim(f"events:{device_id}", 0, 99)

    @staticmethod
    async def _save_to_db(db: AsyncSession, device_id: str, data: Dict[str, Any]):
        """
        将遥测数据保存到数据库

        Args:
            db: 数据库会话
            device_id: 设备ID
            data: 遥测数据，包含 timestamp 和 data

        将数据插入到 telemetry_history 表中
        """
        from sqlalchemy import text
        # 使用原生 SQL 插入遥测历史数据
        stmt = text("""
            INSERT INTO telemetry_history (device_id, timestamp, data)
            VALUES (:device_id, :timestamp, :data)
        """)
        await db.execute(stmt, {
            'device_id': device_id,
            'timestamp': data['timestamp'],
            'data': json.dumps(data['data'])
        })
        await db.commit()

    @staticmethod
    async def get_latest_telemetry(device_id: str) -> Optional[Dict[str, Any]]:
        """
        获取设备的最新遥测数据

        Args:
            device_id: 设备ID

        Returns:
            最新遥测数据，如果不存在返回 None

        从 Redis 中查询，数据保留 300 秒
        """
        data = await redis_client.get(f"telemetry:{device_id}")
        if data:
            return json.loads(data)
        return None

    @staticmethod
    async def get_latest_event(device_id: str) -> Optional[Dict[str, Any]]:
        """
        获取设备的最新事件

        Args:
            device_id: 设备ID

        Returns:
            最新事件数据，如果不存在返回 None

        从 Redis 中查询，数据保留 3600 秒
        """
        data = await redis_client.get(f"event:{device_id}")
        if data:
            return json.loads(data)
        return None

    @staticmethod
    async def get_event_history(device_id: str, limit: int = 10) -> list:
        """
        获取设备的事件历史记录

        Args:
            device_id: 设备ID
            limit: 返回的最大记录数（默认 10）

        Returns:
            事件历史列表

        从 Redis List 中查询，保留最近 100 条
        """
        events = await redis_client.lrange(f"events:{device_id}", 0, limit - 1)
        return [json.loads(e) for e in events]
