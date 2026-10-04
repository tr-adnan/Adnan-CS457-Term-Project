## Serializer/Parser Prompt

I am making a two-player Battleship game in Python using TCP sockets.

Write only the message serializer/parser code for my protocol. Do not write the full client, server, or game logic.

Protocol rules:
- Use TCP
- Messages are JSON
- Encode using UTF-8
- Every message ends with `\n`
- TCP does not preserve message boundaries, so the parser must keep a buffer and handle:
  - one full message in one recv()
  - one message split across multiple recv() calls
  - multiple messages in one recv()
  - one full message followed by part of another

Every message should have this format:

{
  "msg_type": string,
  "player_id": "Player_1", "Player_2", or null,
  "payload": object,
  "timestamp": integer
}

Valid message types:
- CONNECT
- LOBBY_WAIT
- GAME_START
- PLACE_SHIP
- STATE_UPDATE
- MOVE
- MOVE_RESULT
- ERROR
- DISCONNECT
- GAME_OVER

Important payload rules:

CONNECT:
- alias

PLACE_SHIP:
- ship: Carrier, Battleship, Submarine, or Destroyer
- start_row: 0-9
- start_col: 0-9
- orientation: HORIZONTAL or VERTICAL

Ship sizes:
- Carrier = 5
- Battleship = 4
- Submarine = 3
- Destroyer = 2

MOVE:
- row: 0-9
- col: 0-9

MOVE_RESULT:
- row
- col
- result: HIT, MISS, or SUNK
- ship: ship name or null

ERROR:
- code
- message

DISCONNECT:
- reason

GAME_OVER:
- winner: Player_1 or Player_2
- reason: ALL_SHIPS_SUNK or FORFEIT

The parser should reject malformed JSON, unknown message types, missing fields, invalid player IDs, invalid coordinates, invalid ships, and invalid orientations without crashing.

Create:
1. `serialize_message(message: dict) -> bytes`
2. `parse_received_data(buffer: bytes, new_data: bytes) -> tuple[list[dict], bytes]`
3. A `ProtocolError` exception

`serialize_message` should validate the message, convert it to compact JSON, encode it as UTF-8, and add one newline.

`parse_received_data` should combine the old buffer with new data, extract all complete newline-delimited messages, parse them, and return any incomplete bytes for the next recv() call.

Use only the Python standard library and keep the code simple and readable.

Do not add, remove, rename, or change any message types, fields, allowed values, or framing rules.
If something is not defined in this protocol, ask me instead of making up a new rule.