# AI Prompts

## Serializer/Parser Prompt

I am making a two-player Battleship game in Python using TCP sockets.

I only need the code for the message serializer and parser. Do not make the full client, server, or game logic.

Use the following protocol rules:

- Use TCP
- Messages are JSON
- Encode messages using UTF-8
- Every complete message ends with `\n`
- TCP does not keep message boundaries, so the parser needs to keep a buffer

The parser should be able to handle:

- One full message in one `recv()`
- One message split across multiple `recv()` calls
- Multiple complete messages in one `recv()`

Every message should follow this format:

```json
{
  "msg_type": "string",
  "player_id": "Player_1", "Player_2", or null,
  "payload": {},
  "timestamp": integer
}
```

Valid message types are:

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

### Payload Rules

CONNECT:
- alias: string

LOBBY_WAIT:
- message: string

GAME_START:
- opponent_alias: string
- board_size: 10
- phase: SHIP_PLACEMENT

PLACE_SHIP:
- ship: Carrier, Battleship, Submarine, or Destroyer
- start_row: integer from 0-9
- start_col: integer from 0-9
- orientation: HORIZONTAL or VERTICAL

Ship sizes:
- Carrier = 5
- Battleship = 4
- Submarine = 3
- Destroyer = 2

STATE_UPDATE:
- phase: SHIP_PLACEMENT or BATTLE
- active_player: Player_1, Player_2, or null
- own_board: 10x10 array
- opponent_board: 10x10 array
- remaining_own_ships: integer
- remaining_opponent_ships: integer

MOVE:
- row: integer from 0-9
- col: integer from 0-9

MOVE_RESULT:
- row: integer from 0-9
- col: integer from 0-9
- result: HIT, MISS, or SUNK
- ship: ship name or null

ERROR:
- code: string
- message: string

DISCONNECT:
- reason: string

GAME_OVER:
- winner: Player_1 or Player_2
- reason: ALL_SHIPS_SUNK or FORFEIT

The parser should reject invalid messages without crashing. This includes:

- Invalid JSON
- Unknown message types
- Missing required fields
- Invalid player IDs
- Invalid coordinates
- Invalid ship names
- Invalid orientations
- Invalid payload types

Create these:

1. `serialize_message(message: dict) -> bytes`
2. `parse_received_data(buffer: bytes, new_data: bytes) -> tuple[list[dict], bytes]`
3. A `ProtocolError` exception

`serialize_message` should:

- Validate the message first
- Convert it to compact JSON
- Encode it using UTF-8
- Add exactly one newline at the end
- Return bytes

`parse_received_data` should:

- Add the new bytes to the existing buffer
- Find complete messages using `\n`
- Parse all complete messages
- Keep incomplete bytes in the buffer for the next `recv()`
- Return the parsed messages and the remaining buffer

Use only the Python standard library and keep the code simple and readable.

Do not rename, remove, or add message types or fields. Do not change the framing rules or allowed values. If something is not defined here, ask me instead of making up a new rule.
