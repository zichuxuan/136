import json
from datetime import datetime
from typing import Dict, Any, Optional
from uuid import uuid4

from app.core.mqtt_client import mqtt_client
from app.core.redis import redis_client
from app.services.modbus_service import ModbusService


class CommandService:
    """
    命令服务类
    负责处理设备命令的接收、执行和状态管理
    通过 MQTT 接收命令，通过 Redis 缓存命令状态
    """

    @staticmethod
    async def process_command(topic: str, payload: bytes):
        try:
            data = json.loads(payload.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError):
            data = {"raw": payload.decode('utf-8', errors='ignore')}

        parts = topic.split('/')
        if len(parts) >= 5 and parts[0] == 'iot' and parts[1] == 'v1' and parts[2] == 'command' and parts[3] == 'device':
            device_code = parts[4] if len(parts) > 4 else 'unknown'

            command_data = {
                'command_id': data.get('command_id') or f"cmd-{uuid4()}",
                'batch_id': data.get('batch_id'),
                'device_code': device_code,
                'command_type': data.get('command_type', data.get('type', 'unknown')),
                'params': data.get('params', {}),
                'stage': 'received',
                'ts': datetime.utcnow().isoformat() + 'Z',
                'source': data.get('source', {'client_id': 'gateway-main'})
            }

            await redis_client.setex(f"command:{device_code}", 3600, json.dumps(command_data))
            await redis_client.lpush(f"commands:{device_code}", json.dumps(command_data))
            await redis_client.ltrim(f"commands:{device_code}", 0, 99)

            await CommandService._execute_command(device_code, data)

    @staticmethod
    async def _execute_command(device_code: str, command: Dict[str, Any]):
        cmd_type = command.get('command_type', command.get('type', 'unknown'))
        params = command.get('params', {})
        command_id = command.get('command_id') or f"cmd-{uuid4()}"
        batch_id = command.get('batch_id')
        source = command.get('source', {'client_id': 'gateway-main'})

        try:
            await ModbusService.execute_write(params)
            result = {
                'command_id': command_id,
                'batch_id': batch_id,
                'device_code': device_code,
                'command_type': cmd_type,
                'result_code': 'EXECUTED',
                'result_message': 'write success',
                'stage': 'executed',
                'ts': datetime.utcnow().isoformat() + 'Z',
                'source': source
            }
        except Exception as exc:  # noqa: BLE001
            result = {
                'command_id': command_id,
                'batch_id': batch_id,
                'device_code': device_code,
                'command_type': cmd_type,
                'result_code': 'FAILED',
                'result_message': str(exc),
                'stage': 'failed',
                'ts': datetime.utcnow().isoformat() + 'Z',
                'source': source
            }

        await mqtt_client.publish(
            f"iot/v1/command-result/device/{device_code}",
            json.dumps(result)
        )
        await redis_client.setex(f"command_result:{device_code}", 3600, json.dumps(result))

    @staticmethod
    async def send_command(
        device_code: str,
        command_type: str,
        params: Dict[str, Any],
        command_id: Optional[str] = None,
        batch_id: Optional[str] = None,
        source: Optional[Dict[str, Any]] = None,
        ts: Optional[str] = None,
    ) -> bool:
        command = {
            'command_id': command_id or f"cmd-{uuid4()}",
            'batch_id': batch_id,
            'device_code': device_code,
            'action_name': command_type,
            'command_type': command_type,
            'params': params,
            'ts': ts or (datetime.utcnow().isoformat() + 'Z'),
            'source': source or {'client_id': 'hmi-http-api'}
        }

        await mqtt_client.publish(f"iot/v1/command/device/{device_code}", json.dumps(command))
        return True

    @staticmethod
    async def get_latest_command(device_id: str) -> Optional[Dict[str, Any]]:
        data = await redis_client.get(f"command:{device_id}")
        if data:
            return json.loads(data)
        return None

    @staticmethod
    async def get_command_history(device_id: str, limit: int = 10) -> list:
        commands = await redis_client.lrange(f"commands:{device_id}", 0, limit - 1)
        return [json.loads(c) for c in commands]

    @staticmethod
    async def get_command_result(device_id: str) -> Optional[Dict[str, Any]]:
        data = await redis_client.get(f"command_result:{device_id}")
        if data:
            return json.loads(data)
        return None
