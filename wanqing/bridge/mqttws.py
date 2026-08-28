"""
mqttws — 零第三方依赖的 MQTT-over-WebSocket 客户端（stdlib only）

晚晴项目共用模块：reminder-pusher 与 family API 均通过它连接
rorolee 的 MQTT broker（ws://mqtt.deotaland.ai:8083/mqtt），
实现主动下行推送（提醒 / 家人留言）。

仅实现客户端所需子集：CONNECT / SUBSCRIBE / PUBLISH / 接收 PUBLISH。
"""

import base64
import os
import socket
import struct


class MQTTWebSocket:
    def __init__(self, broker, port):
        self.broker = broker
        self.port = port
        self.sock = None
        self._msg_id = 0

    def connect(self, client_id=None):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(15)
        self.sock.connect((self.broker, self.port))
        key = base64.b64encode(os.urandom(16)).decode()
        req = (
            f'GET /mqtt HTTP/1.1\r\n'
            f'Host: {self.broker}:{self.port}\r\n'
            f'Upgrade: websocket\r\n'
            f'Connection: Upgrade\r\n'
            f'Sec-WebSocket-Key: {key}\r\n'
            f'Sec-WebSocket-Version: 13\r\n'
            f'Sec-WebSocket-Protocol: mqtt\r\n'
            f'\r\n'
        )
        self.sock.send(req.encode())
        resp = self.sock.recv(4096).decode()
        if '101' not in resp:
            raise Exception('WebSocket upgrade failed')
        cid = client_id or f'mqttws-{os.getpid()}'
        self._ws_send(self._mqtt_connect(cid))
        data = self._ws_recv()
        if not data or data[0] != 0x20 or data[3] != 0:
            raise Exception(f'MQTT CONNACK failed: {data!r}')

    def subscribe(self, topic, qos=0):
        self._msg_id += 1
        self._ws_send(self._mqtt_subscribe(topic, qos, self._msg_id))
        self._ws_recv()

    def publish(self, topic, message, qos=0):
        self._ws_send(self._mqtt_publish(topic, message, qos))

    def recv_message(self, timeout=1):
        """接收 PUBLISH。返回 (topic, payload) 或 None。"""
        self.sock.settimeout(timeout)
        try:
            data = self._ws_recv()
            if data and (data[0] & 0xF0) == 0x30:
                qos = (data[0] >> 1) & 0x03
                topic_len = struct.unpack('>H', data[2:4])[0]
                topic = data[4:4+topic_len].decode('utf-8', errors='replace')
                offset = 4 + topic_len
                if qos > 0:
                    offset += 2
                payload = data[offset:].decode('utf-8', errors='replace')
                return topic, payload
            return None
        except socket.timeout:
            return None
        except Exception:
            return None

    def _ws_send(self, data):
        frame = bytearray([0x82])
        mask_key = os.urandom(4)
        length = len(data)
        if length < 126:
            frame.append(0x80 | length)
        elif length < 65536:
            frame.append(0x80 | 126)
            frame.extend(struct.pack('>H', length))
        else:
            frame.append(0x80 | 127)
            frame.extend(struct.pack('>Q', length))
        frame.extend(mask_key)
        masked = bytes(b ^ mask_key[i % 4] for i, b in enumerate(data))
        frame.extend(masked)
        self.sock.send(frame)

    def _ws_recv(self):
        header = self.sock.recv(2)
        if len(header) < 2:
            return None
        masked = (header[1] & 0x80) != 0
        length = header[1] & 0x7F
        if length == 126:
            length = struct.unpack('>H', self.sock.recv(2))[0]
        elif length == 127:
            length = struct.unpack('>Q', self.sock.recv(8))[0]
        if masked:
            mask = self.sock.recv(4)
        data = b''
        while len(data) < length:
            chunk = self.sock.recv(min(length - len(data), 65536))
            if not chunk:
                break
            data += chunk
        if masked:
            data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
        return data

    def _mqtt_connect(self, client_id):
        cid = client_id.encode()
        variable = b'\x00\x04MQTT\x04\x02\x00\x3c'
        payload = struct.pack('>H', len(cid)) + cid
        remaining = variable + payload
        header = bytearray([0x10])
        l = len(remaining)
        while l > 0:
            byte = l % 128; l //= 128
            if l > 0: byte |= 0x80
            header.append(byte)
        return bytes(header) + remaining

    def _mqtt_subscribe(self, topic, qos, msg_id):
        variable = struct.pack('>H', msg_id)
        t = topic.encode()
        payload = struct.pack('>H', len(t)) + t + bytes([qos])
        remaining = variable + payload
        header = bytearray([0x82])
        l = len(remaining)
        while l > 0:
            byte = l % 128; l //= 128
            if l > 0: byte |= 0x80
            header.append(byte)
        return bytes(header) + remaining

    def _mqtt_publish(self, topic, message, qos):
        t = topic.encode()
        variable = struct.pack('>H', len(t)) + t
        if qos > 0:
            self._msg_id += 1
            variable += struct.pack('>H', self._msg_id)
        payload = message.encode('utf-8')
        remaining = variable + payload
        header_byte = 0x30 | (qos << 1)
        header = bytearray([header_byte])
        l = len(remaining)
        while l > 0:
            byte = l % 128; l //= 128
            if l > 0: byte |= 0x80
            header.append(byte)
        return bytes(header) + remaining

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
