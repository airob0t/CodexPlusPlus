from __future__ import annotations

import base64
import hashlib
import json
import os
import socket
import ssl
import struct
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse
from urllib.request import build_opener, ProxyHandler


BridgeHandler = Callable[[str, dict[str, object]], dict[str, object]]
BRIDGE_BINDING_NAME = "codexSessionDeleteV2"


class WebSocketTimeoutException(TimeoutError):
    pass


@dataclass
class _SimpleWebSocket:
    sock: socket.socket

    def send(self, payload: str) -> None:
        data = payload.encode("utf-8")
        frame = bytearray()
        frame.append(0x80 | 0x1)
        mask_bit = 0x80
        length = len(data)
        if length < 126:
            frame.append(mask_bit | length)
        elif length < (1 << 16):
            frame.append(mask_bit | 126)
            frame.extend(struct.pack("!H", length))
        else:
            frame.append(mask_bit | 127)
            frame.extend(struct.pack("!Q", length))
        mask = os.urandom(4)
        frame.extend(mask)
        frame.extend(bytes(b ^ mask[i % 4] for i, b in enumerate(data)))
        self.sock.sendall(frame)

    def recv(self) -> str:
        while True:
            try:
                first = _recv_exact(self.sock, 2)
                fin_opcode = first[0]
                masked_len = first[1]
                opcode = fin_opcode & 0x0F
                masked = bool(masked_len & 0x80)
                length = masked_len & 0x7F
                if length == 126:
                    length = struct.unpack("!H", _recv_exact(self.sock, 2))[0]
                elif length == 127:
                    length = struct.unpack("!Q", _recv_exact(self.sock, 8))[0]
                mask = _recv_exact(self.sock, 4) if masked else b""
                data = _recv_exact(self.sock, length) if length else b""
            except socket.timeout as exc:
                raise WebSocketTimeoutException("idle") from exc

            if masked and mask:
                data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
            if opcode == 0x8:
                raise ConnectionError("websocket closed")
            if opcode == 0x9:
                self._send_control(0xA, data)
                continue
            if opcode == 0xA:
                continue
            if opcode in {0x1, 0x0}:
                return data.decode("utf-8", errors="replace")

    def close(self) -> None:
        try:
            self._send_control(0x8, b"")
        except Exception:
            pass
        try:
            self.sock.close()
        except Exception:
            pass

    def _send_control(self, opcode: int, data: bytes) -> None:
        frame = bytearray()
        frame.append(0x80 | opcode)
        mask_bit = 0x80
        length = len(data)
        if length < 126:
            frame.append(mask_bit | length)
        elif length < (1 << 16):
            frame.append(mask_bit | 126)
            frame.extend(struct.pack("!H", length))
        else:
            frame.append(mask_bit | 127)
            frame.extend(struct.pack("!Q", length))
        mask = os.urandom(4)
        frame.extend(mask)
        frame.extend(bytes(b ^ mask[i % 4] for i, b in enumerate(data)))
        self.sock.sendall(frame)


def list_targets(port: int) -> list[dict[str, object]]:
    opener = build_opener(ProxyHandler({}))
    with opener.open(f"http://127.0.0.1:{port}/json", timeout=3) as response:
        return json.loads(response.read().decode("utf-8"))


def pick_page_target(targets: list[dict[str, object]]) -> dict[str, object]:
    pages = [target for target in targets if target.get("type") == "page" and target.get("webSocketDebuggerUrl")]
    for target in pages:
        title = str(target.get("title", ""))
        url = str(target.get("url", ""))
        if "codex" in (title + " " + url).lower():
            return target
    if pages:
        return pages[0]
    raise RuntimeError("No injectable Codex page target found")


def _connect_websocket(websocket_url: str, timeout: float = 5.0) -> _SimpleWebSocket:
    parsed = urlparse(websocket_url)
    if parsed.scheme not in {"ws", "wss"}:
        raise ValueError(f"Unsupported websocket url: {websocket_url}")
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if parsed.scheme == "wss" else 80)
    sock = socket.create_connection((host, port), timeout=timeout)
    sock.settimeout(timeout)
    if parsed.scheme == "wss":
        context = ssl.create_default_context()
        sock = context.wrap_socket(sock, server_hostname=host)
        sock.settimeout(timeout)

    key = base64.b64encode(os.urandom(16)).decode("ascii")
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    request = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n\r\n"
    )
    sock.sendall(request.encode("ascii"))
    response = _read_http_headers(sock)
    if " 101 " not in response.splitlines()[0]:
        raise RuntimeError(f"WebSocket handshake failed: {response.splitlines()[0] if response else 'empty response'}")
    accept = ""
    for line in response.split("\r\n")[1:]:
        if line.lower().startswith("sec-websocket-accept:"):
            accept = line.split(":", 1)[1].strip()
            break
    expected = base64.b64encode(
        hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")).digest()
    ).decode("ascii")
    if accept != expected:
        raise RuntimeError("WebSocket handshake validation failed")
    return _SimpleWebSocket(sock)


def evaluate_script(websocket_url: str, script: str) -> dict[str, object]:
    ws = _connect_websocket(websocket_url, timeout=5)
    try:
        payload = {
            "id": 1,
            "method": "Runtime.evaluate",
            "params": {"expression": script, "awaitPromise": False, "allowUnsafeEvalBlockedByCSP": True},
        }
        ws.send(json.dumps(payload))
        while True:
            message = json.loads(ws.recv())
            if message.get("id") == 1:
                if "error" in message:
                    raise RuntimeError(str(message["error"]))
                return message
    finally:
        ws.close()


def build_bridge_script(binding_name: str) -> str:
    return f"""
(() => {{
  window.__codexSessionDeleteCallbacks = new Map();
  window.__codexSessionDeleteSeq = 0;
  window.__codexSessionDeleteResolve = (id, result) => {{
    const callback = window.__codexSessionDeleteCallbacks.get(id);
    if (!callback) return;
    window.__codexSessionDeleteCallbacks.delete(id);
    callback.resolve(result);
  }};
  window.__codexSessionDeleteReject = (id, message) => {{
    const callback = window.__codexSessionDeleteCallbacks.get(id);
    if (!callback) return;
    window.__codexSessionDeleteCallbacks.delete(id);
    callback.resolve({{ status: "failed", message }});
  }};
  window.__codexSessionDeleteBridge = (path, payload) => new Promise((resolve) => {{
    const id = String(++window.__codexSessionDeleteSeq);
    window.__codexSessionDeleteCallbacks.set(id, {{ resolve }});
    window.{binding_name}(JSON.stringify({{ id, path, payload }}));
  }});
}})();
"""


def install_bridge(websocket_url: str, binding_name: str, handler: BridgeHandler) -> _SimpleWebSocket:
    ws = _connect_websocket(websocket_url, timeout=5)
    ws.send(json.dumps({"id": 1, "method": "Runtime.addBinding", "params": {"name": binding_name}}))
    _wait_for_id(ws, 1)
    ws.send(json.dumps({"id": 2, "method": "Runtime.evaluate", "params": {"expression": build_bridge_script(binding_name), "awaitPromise": False, "allowUnsafeEvalBlockedByCSP": True}}))
    _wait_for_id(ws, 2)
    thread = threading.Thread(target=_bridge_loop, args=(ws, handler), daemon=True)
    thread.start()
    return ws


def inject_file(port: int, script_path: Path, helper_port: int, handler: BridgeHandler | None = None) -> _SimpleWebSocket | dict[str, object]:
    targets = list_targets(port)
    target = pick_page_target(targets)
    websocket_url = str(target["webSocketDebuggerUrl"])
    bridge_socket = install_bridge(websocket_url, BRIDGE_BINDING_NAME, handler) if handler else None
    script = script_path.read_text(encoding="utf-8")
    prefix = f"window.__CODEX_SESSION_DELETE_HELPER__ = 'http://127.0.0.1:{helper_port}';\n"
    result = evaluate_script(websocket_url, prefix + script)
    return bridge_socket or result


def _bridge_loop(ws: _SimpleWebSocket, handler: BridgeHandler) -> None:
    while True:
        try:
            message = json.loads(ws.recv())
        except WebSocketTimeoutException:
            continue
        except Exception:
            return
        if message.get("method") != "Runtime.bindingCalled":
            continue
        params = message.get("params", {})
        try:
            payload = json.loads(str(params.get("payload", "{}")))
            request_id = str(payload["id"])
            result = handler(str(payload["path"]), dict(payload.get("payload", {})))
            _resolve_bridge(ws, request_id, result)
        except Exception as exc:
            request_id = str(locals().get("payload", {}).get("id", ""))
            if request_id:
                _reject_bridge(ws, request_id, str(exc))


def _resolve_bridge(ws: _SimpleWebSocket, request_id: str, result: dict[str, object]) -> None:
    expression = f"window.__codexSessionDeleteResolve({json.dumps(request_id)}, {json.dumps(result)})"
    ws.send(json.dumps({"id": _next_id(), "method": "Runtime.evaluate", "params": {"expression": expression, "awaitPromise": False, "allowUnsafeEvalBlockedByCSP": True}}))


def _reject_bridge(ws: _SimpleWebSocket, request_id: str, message: str) -> None:
    expression = f"window.__codexSessionDeleteReject({json.dumps(request_id)}, {json.dumps(message)})"
    ws.send(json.dumps({"id": _next_id(), "method": "Runtime.evaluate", "params": {"expression": expression, "awaitPromise": False, "allowUnsafeEvalBlockedByCSP": True}}))


def _wait_for_id(ws: _SimpleWebSocket, message_id: int) -> dict[str, object]:
    while True:
        message = json.loads(ws.recv())
        if message.get("id") == message_id:
            if "error" in message:
                raise RuntimeError(str(message["error"]))
            return message


_id_lock = threading.Lock()
_id = 100


def _next_id() -> int:
    global _id
    with _id_lock:
        _id += 1
        return _id


def _recv_exact(sock: socket.socket, size: int) -> bytes:
    buf = bytearray()
    while len(buf) < size:
        chunk = sock.recv(size - len(buf))
        if not chunk:
            raise ConnectionError("socket closed")
        buf.extend(chunk)
    return bytes(buf)


def _read_http_headers(sock: socket.socket) -> str:
    data = bytearray()
    while b"\r\n\r\n" not in data:
        chunk = sock.recv(4096)
        if not chunk:
            raise ConnectionError("socket closed during handshake")
        data.extend(chunk)
    header_bytes = bytes(data.split(b"\r\n\r\n", 1)[0])
    return header_bytes.decode("iso-8859-1")
