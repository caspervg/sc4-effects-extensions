"""Tiny client for SC4's built-in network game-command listener."""

from __future__ import annotations

import http.client

HOST = "127.0.0.1"
PORT = 50020


def quote_argument(value: object) -> str:
    text = str(value)
    if '"' in text:
        raise ValueError('game-command arguments cannot contain a double quote')
    if not text or any(ch.isspace() for ch in text):
        return f'"{text}"'
    return text


def make_command(name: str, *args: object) -> str:
    return " ".join((name, *(quote_argument(arg) for arg in args)))


def send_command(command: str, *, timeout: float = 30.0) -> str:
    try:
        data = command.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValueError("SC4 game commands must contain only ASCII characters") from exc
    connection = http.client.HTTPConnection(HOST, PORT, timeout=timeout)
    try:
        try:
            connection.request("POST", "/", body=data)
            response = connection.getresponse()
            result = response.read()
        except OSError as exc:
            raise ConnectionError(
                f"Could not connect to SC4's command server: {exc}. "
                "Start SimCity 4 with -NetCommandGenerator:enabled."
            ) from exc
        if response.status >= 400:
            raise ConnectionError(f"SC4 command server returned HTTP {response.status} {response.reason}")
    finally:
        connection.close()
    text = result.decode("utf-8", errors="replace").strip()
    marker = "\nResult:\n"
    return text.partition(marker)[2].strip() if marker in text else text
