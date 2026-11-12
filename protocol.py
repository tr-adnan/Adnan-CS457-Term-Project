
"""Shared, newline-delimited JSON protocol"""

import json
import time


BOARD_SIZE = 10
SHIP_SIZES = {"Carrier": 5, "Battleship": 4, "Submarine": 3, "Destroyer": 2}
MESSAGE_TYPES = {
    "CONNECT", "LOBBY_WAIT", "GAME_START", "PLACE_SHIP", "STATE_UPDATE",
    "MOVE", "MOVE_RESULT", "ERROR", "DISCONNECT", "GAME_OVER",
}
PLAYER_IDS = {"Player_1", "Player_2"}
MAX_MESSAGE_BYTES = 65536


class ProtocolError(ValueError):
    """Raised when a protocol message is malformed or invalid."""


def _integer(value, minimum=None, maximum=None):
    if type(value) is not int:
        return False
    return (minimum is None or value >= minimum) and (maximum is None or value <= maximum)


def _exact_keys(payload, keys):
    return isinstance(payload, dict) and set(payload) == set(keys)


def _board(value, allowed):
    return (
        isinstance(value, list)
        and len(value) == BOARD_SIZE
        and all(
            isinstance(row, list)
            and len(row) == BOARD_SIZE
            and all(isinstance(cell, str) and cell in allowed for cell in row)
            for row in value
        )
    )


def validate_message(message):
    """Validate the envelope and exact payload schema from protocol_blueprint.md."""
    if not isinstance(message, dict) or set(message) != {
        "msg_type", "player_id", "payload", "timestamp"
    }:
        raise ProtocolError("Message must contain msg_type, player_id, payload, and timestamp.")

    kind = message["msg_type"]
    player_id = message["player_id"]
    payload = message["payload"]

    if not isinstance(kind, str) or kind not in MESSAGE_TYPES:
        raise ProtocolError("Unknown message type.")
    if player_id is not None and (not isinstance(player_id, str) or player_id not in PLAYER_IDS):
        raise ProtocolError("Invalid player ID.")
    if not _integer(message["timestamp"], minimum=0):
        raise ProtocolError("Timestamp must be a nonnegative integer.")
    if not isinstance(payload, dict):
        raise ProtocolError("Payload must be a JSON object.")

    valid = False

    if kind == "CONNECT":
        valid = (
            _exact_keys(payload, ("alias",))
            and isinstance(payload["alias"], str)
            and bool(payload["alias"].strip())
        )

    elif kind == "LOBBY_WAIT":
        valid = (
            _exact_keys(payload, ("message",))
            and isinstance(payload["message"], str)
        )

    elif kind == "GAME_START":
        valid = (
            _exact_keys(payload, ("opponent_alias", "board_size", "phase"))
            and isinstance(payload["opponent_alias"], str)
            and _integer(payload["board_size"], 10, 10)
            and payload["phase"] == "SHIP_PLACEMENT"
        )

    elif kind == "PLACE_SHIP":
        valid = (
            _exact_keys(payload, ("ship", "start_row", "start_col", "orientation"))
            and isinstance(payload["ship"], str) and payload["ship"] in SHIP_SIZES
            and _integer(payload["start_row"], 0, 9)
            and _integer(payload["start_col"], 0, 9)
            and payload["orientation"] in ("HORIZONTAL", "VERTICAL")
        )

    elif kind == "STATE_UPDATE":
        valid = (
            _exact_keys(payload, (
                "phase", "active_player", "own_board", "opponent_board",
                "remaining_own_ships", "remaining_opponent_ships"
            ))
            and payload["phase"] in ("SHIP_PLACEMENT", "BATTLE")
            and (
                payload["active_player"] is None
                or (
                    isinstance(payload["active_player"], str)
                    and payload["active_player"] in PLAYER_IDS
                )
            )
            and _board(payload["own_board"], {"EMPTY", "SHIP", "HIT", "MISS", "SUNK"})
            and _board(payload["opponent_board"], {"UNKNOWN", "HIT", "MISS", "SUNK"})
            and _integer(payload["remaining_own_ships"], 0, 4)
            and _integer(payload["remaining_opponent_ships"], 0, 4)
        )

    elif kind == "MOVE":
        valid = (
            _exact_keys(payload, ("row", "col"))
            and _integer(payload["row"], 0, 9)
            and _integer(payload["col"], 0, 9)
        )

    elif kind == "MOVE_RESULT":
        valid = (
            _exact_keys(payload, ("row", "col", "result", "ship"))
            and _integer(payload["row"], 0, 9)
            and _integer(payload["col"], 0, 9)
            and payload["result"] in ("HIT", "MISS", "SUNK")
            and (
                payload["ship"] is None
                or (
                    isinstance(payload["ship"], str)
                    and payload["ship"] in SHIP_SIZES
                )
            )
        )

    elif kind == "ERROR":
        valid = (
            _exact_keys(payload, ("code", "message"))
            and all(isinstance(payload[k], str) for k in ("code", "message"))
        )

    elif kind == "DISCONNECT":
        valid = (
            _exact_keys(payload, ("reason",))
            and isinstance(payload["reason"], str)
        )

    elif kind == "GAME_OVER":
        valid = (
            _exact_keys(payload, ("winner", "reason"))
            and isinstance(payload["winner"], str)
            and payload["winner"] in PLAYER_IDS
            and payload["reason"] in ("ALL_SHIPS_SUNK", "FORFEIT")
        )

    if not valid:
        raise ProtocolError("Invalid payload for {}.".format(kind))

    return message


def make_message(msg_type, player_id, payload):
    """Build a message without adding fields beyond the Sprint 1 blueprint."""
    message = {
        "msg_type": msg_type,
        "player_id": player_id,
        "payload": payload,
        "timestamp": int(time.time()),
    }
    validate_message(message)
    return message


def serialize_message(message):
    """Validate, encode as UTF-8 compact JSON, and add one newline."""
    validate_message(message)
    data = json.dumps(
        message, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")

    if len(data) > MAX_MESSAGE_BYTES:
        raise ProtocolError("Message exceeds maximum size.")

    return data + b"\n"


def decode_frame(frame):
    """Decode a complete JSON frame without the trailing newline."""
    if len(frame) > MAX_MESSAGE_BYTES:
        raise ProtocolError("Message exceeds maximum size.")

    try:
        message = json.loads(frame.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise ProtocolError("Invalid UTF-8 or JSON message.") from exc

    return validate_message(message)


def parse_received_data(buffer, new_data):
    """Return all complete messages plus any incomplete remaining TCP bytes."""
    buffer += new_data
    messages = []

    while b"\n" in buffer:
        frame, buffer = buffer.split(b"\n", 1)
        messages.append(decode_frame(frame))

    if len(buffer) > MAX_MESSAGE_BYTES:
        raise ProtocolError("Incomplete message exceeds maximum size.")

    return messages, buffer
