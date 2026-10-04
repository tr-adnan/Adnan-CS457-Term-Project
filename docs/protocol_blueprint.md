# Application Protocol Blueprint

## 1. Protocol Overview

This project uses a custom application-layer protocol for a two-player Battleship game. The clients communicate with the game server using TCP.

- **Transport Protocol:** TCP
- **Serialization Format:** JSON
- **Encoding:** UTF-8
- **Framing:** Newline-delimited JSON (`\n`)
- **Board Size:** 10 x 10
- **Coordinates:** Rows and columns use integers from 0 through 9.

Each player has four ships:

| Ship | Size |
|---|---:|
| Carrier | 5 |
| Battleship | 4 |
| Submarine | 3 |
| Destroyer | 2 |

---

## 2. TCP Message Framing

TCP provides a continuous byte stream and does not preserve individual message boundaries. A single `recv()` may contain one complete message, part of a message, or multiple messages.

To determine message boundaries, every JSON message is encoded using UTF-8 and ends with one newline character (`\n`).

Example message on the wire:

```text
{"msg_type":"MOVE","player_id":"Player_1","payload":{"row":2,"col":4},"timestamp":1791070000}\n
```

The receiver keeps incoming bytes in a buffer. Whenever a newline is found, the bytes before the newline are extracted and parsed as one complete JSON message. Any incomplete bytes remain in the buffer until more data is received.

### Back-to-Back Message Example

Two messages may arrive together in one TCP receive:

```text
{"msg_type":"MOVE","player_id":"Player_1","payload":{"row":2,"col":4},"timestamp":1791070000}\n{"msg_type":"MOVE","player_id":"Player_2","payload":{"row":5,"col":7},"timestamp":1791070005}\n
```

The receiver separates the stream at each newline and processes the two messages individually.

### Fragmented Message Example

A single message may also be split between multiple TCP receives.

First receive:

```text
{"msg_type":"MOVE","player_id":"Player_1","payload":{"row":2,
```

Second receive:

```text
"col":4},"timestamp":1791070000}\n
```

The first part remains in the receive buffer because no newline has been received yet. After the second part arrives, the complete message can be extracted and parsed.

---

## 3. Common Message Structure

All protocol messages use the following general structure:

```json
{
  "msg_type": "MESSAGE_TYPE",
  "player_id": "Player_1",
  "payload": {},
  "timestamp": 1791070000
}
```

| Field | Type | Description |
|---|---|---|
| `msg_type` | string | Identifies the type of protocol message |
| `player_id` | string or null | `Player_1`, `Player_2`, or `null` before assignment |
| `payload` | object | Data specific to the message |
| `timestamp` | integer | Unix timestamp in seconds |

Valid message types are:

- `CONNECT`
- `LOBBY_WAIT`
- `GAME_START`
- `PLACE_SHIP`
- `STATE_UPDATE`
- `MOVE`
- `MOVE_RESULT`
- `ERROR`
- `DISCONNECT`
- `GAME_OVER`

---

## 4. Message Types

### 4.1 CONNECT

**Direction:** Client → Server

**Purpose:** Requests to join the Battleship game. The client has not yet been assigned a player ID.

#### Payload

| Field | Type | Description |
|---|---|---|
| `alias` | string | Player's chosen display name |

#### Example

```json
{
  "msg_type": "CONNECT",
  "player_id": null,
  "payload": {
    "alias": "Adnan"
  },
  "timestamp": 1791070000
}
```

The first accepted client becomes `Player_1`. The second accepted client becomes `Player_2`.

---

### 4.2 LOBBY_WAIT

**Direction:** Server → Client

**Purpose:** Tells the first connected player that the server is waiting for a second player.

#### Payload

| Field | Type | Description |
|---|---|---|
| `message` | string | Waiting message displayed to the player |

#### Example

```json
{
  "msg_type": "LOBBY_WAIT",
  "player_id": "Player_1",
  "payload": {
    "message": "Waiting for Player 2 to connect."
  },
  "timestamp": 1791070002
}
```

---

### 4.3 GAME_START

**Direction:** Server → Clients

**Purpose:** Tells both players that two clients are connected and that the game can begin with ship placement.

#### Payload

| Field | Type | Description |
|---|---|---|
| `opponent_alias` | string | Alias of the other player |
| `board_size` | integer | Board width and height |
| `phase` | string | Current game phase |

`phase` is initially:

```text
SHIP_PLACEMENT
```

#### Example

```json
{
  "msg_type": "GAME_START",
  "player_id": "Player_1",
  "payload": {
    "opponent_alias": "PlayerTwo",
    "board_size": 10,
    "phase": "SHIP_PLACEMENT"
  },
  "timestamp": 1791070010
}
```

---

### 4.4 PLACE_SHIP

**Direction:** Client → Server

**Purpose:** Places one of the player's ships on the board.

#### Payload

| Field | Type | Allowed Values |
|---|---|---|
| `ship` | string | `Carrier`, `Battleship`, `Submarine`, `Destroyer` |
| `start_row` | integer | 0-9 |
| `start_col` | integer | 0-9 |
| `orientation` | string | `HORIZONTAL` or `VERTICAL` |

Ship sizes are:

- Carrier = 5
- Battleship = 4
- Submarine = 3
- Destroyer = 2

The server rejects a placement if:

- The ship would extend outside the board.
- The ship overlaps another ship.
- The player already placed that ship.
- The ship name or orientation is invalid.

#### Example

```json
{
  "msg_type": "PLACE_SHIP",
  "player_id": "Player_1",
  "payload": {
    "ship": "Carrier",
    "start_row": 2,
    "start_col": 1,
    "orientation": "HORIZONTAL"
  },
  "timestamp": 1791070020
}
```

This example places the Carrier at:

```text
(2,1)
(2,2)
(2,3)
(2,4)
(2,5)
```

Once both players have placed all four ships, the server enters the battle phase and Player 1 receives the first turn.

---

### 4.5 STATE_UPDATE

**Direction:** Server → Clients

**Purpose:** Sends updated game information after important changes such as ship placement or an attack.

Each client receives a version of the state that is safe for that player to view.

#### Payload

| Field | Type | Description |
|---|---|---|
| `phase` | string | `SHIP_PLACEMENT` or `BATTLE` |
| `active_player` | string or null | `Player_1`, `Player_2`, or `null` during placement |
| `own_board` | array | Player's own 10 x 10 board |
| `opponent_board` | array | Known information about opponent's 10 x 10 board |
| `remaining_own_ships` | integer | Number of player's ships that have not been sunk |
| `remaining_opponent_ships` | integer | Number of opponent's ships that have not been sunk |

The player's own board may contain:

- `EMPTY`
- `SHIP`
- `HIT`
- `MISS`

The opponent board may contain:

- `UNKNOWN`
- `HIT`
- `MISS`

The opponent board must never reveal an opponent ship that has not already been hit.

#### Example

```json
{
  "msg_type": "STATE_UPDATE",
  "player_id": "Player_1",
  "payload": {
    "phase": "BATTLE",
    "active_player": "Player_1",
    "own_board": [],
    "opponent_board": [],
    "remaining_own_ships": 4,
    "remaining_opponent_ships": 4
  },
  "timestamp": 1791070030
}
```

The empty arrays in this example are shortened representations. During the game, each board contains the complete 10 x 10 board state.

---

### 4.6 MOVE

**Direction:** Client → Server

**Purpose:** Allows the active player to attack one coordinate on the opponent's board.

#### Payload

| Field | Type | Allowed Values |
|---|---|---|
| `row` | integer | 0-9 |
| `col` | integer | 0-9 |

#### Example

```json
{
  "msg_type": "MOVE",
  "player_id": "Player_1",
  "payload": {
    "row": 2,
    "col": 4
  },
  "timestamp": 1791070040
}
```

A move is rejected if:

- The coordinates are outside the board.
- The coordinate has already been attacked.
- The message comes from a player whose turn is not active.

An invalid move does not change the active player.

---

### 4.7 MOVE_RESULT

**Direction:** Server → Clients

**Purpose:** Reports the result of an attack.

#### Payload

| Field | Type | Description |
|---|---|---|
| `row` | integer | Attacked row |
| `col` | integer | Attacked column |
| `result` | string | `HIT`, `MISS`, or `SUNK` |
| `ship` | string or null | Name of the ship when applicable |

#### Example

```json
{
  "msg_type": "MOVE_RESULT",
  "player_id": "Player_1",
  "payload": {
    "row": 2,
    "col": 4,
    "result": "HIT",
    "ship": "Carrier"
  },
  "timestamp": 1791070041
}
```

If the attack does not end the game, the server updates the game state and switches the active player.

---

### 4.8 ERROR

**Direction:** Server → Client

**Purpose:** Reports an invalid or malformed request without crashing or ending the game.

Possible errors include:

- Invalid coordinates
- Repeated attack
- Out-of-turn move
- Invalid ship placement
- Missing fields
- Malformed JSON
- Unknown message type

#### Payload

| Field | Type | Description |
|---|---|---|
| `code` | string | Short error identifier |
| `message` | string | Human-readable description |

#### Example

```json
{
  "msg_type": "ERROR",
  "player_id": "Player_2",
  "payload": {
    "code": "OUT_OF_TURN",
    "message": "It is not your turn."
  },
  "timestamp": 1791070045
}
```

For an invalid move, the server sends an `ERROR` message and remains on the same player's turn.

---

### 4.9 DISCONNECT

**Direction:** Client → Server or Server → Client

**Purpose:** Represents an intentional application-level connection termination.

#### Payload

| Field | Type | Description |
|---|---|---|
| `reason` | string | Reason the connection is being closed |

#### Example

```json
{
  "msg_type": "DISCONNECT",
  "player_id": "Player_1",
  "payload": {
    "reason": "Player quit the game."
  },
  "timestamp": 1791070050
}
```

If a player intentionally disconnects during a game, the opponent wins by forfeit.

If a player disconnects before the game begins, that player is removed and the server returns to or remains in `WAITING_FOR_PLAYERS`.

---

### 4.10 GAME_OVER

**Direction:** Server → Clients

**Purpose:** Announces the final result of the game.

#### Payload

| Field | Type | Allowed Values |
|---|---|---|
| `winner` | string | `Player_1` or `Player_2` |
| `reason` | string | `ALL_SHIPS_SUNK` or `FORFEIT` |

#### Example

```json
{
  "msg_type": "GAME_OVER",
  "player_id": "Player_2",
  "payload": {
    "winner": "Player_2",
    "reason": "ALL_SHIPS_SUNK"
  },
  "timestamp": 1791070100
}
```

After `GAME_OVER`, the server enters the `CLEANUP` state. The current client connections are closed, the boards and player information are cleared, and the server returns to `WAITING_FOR_PLAYERS` so another game can begin.

---

## 5. Invalid and Malformed Messages

Messages are rejected when they contain:

- Invalid UTF-8
- Invalid JSON
- Missing required fields
- Unknown `msg_type`
- Invalid `player_id`
- Invalid payload data types
- Coordinates outside 0-9
- Invalid ship names
- Invalid ship orientation

Malformed messages must not crash the server.

When enough information is available to respond to the client, the server sends an `ERROR` message explaining the problem.

---

## 6. Connection Termination and Socket Lifecycle

The protocol handles both intentional application-level disconnections and TCP-level connection failures.

### 6.1 Application-Level Disconnect

A client that intentionally leaves the game sends a `DISCONNECT` message before closing its socket.

If this happens during a game:

1. The server receives `DISCONNECT`.
2. The opponent is declared the winner by forfeit.
3. The server sends `GAME_OVER` to the remaining player.
4. The server enters `CLEANUP`.
5. Both client connections are closed.
6. The current game state is cleared.
7. The server returns to `WAITING_FOR_PLAYERS`.

If a player sends `DISCONNECT` before the game begins, the server removes that player and continues waiting for clients.

---

### 6.2 TCP EOF (0-Byte) Rule

When a remote client closes its TCP connection cleanly, calling `recv()` does not raise an exception.

Instead, `recv()` returns zero bytes:

```python
b""
```

This represents EOF (End-of-File) and indicates that the remote peer closed its side of the connection.

The receive loop must check for this condition. Otherwise, continuing to call `recv()` after EOF may result in an infinite loop because the call will continue returning `b""`.

Example:

```python
data = sock.recv(4096)

if not data:
    # Remote peer closed connection cleanly
    sock.close()
    handle_client_disconnect(player_id)
```

If EOF occurs during a game, the disconnect is treated as a forfeit.

If EOF occurs before the game begins, the disconnected player is removed and the server continues waiting for players.

---

### 6.3 Abrupt Connection Loss

A client may also disappear because of a program crash, TCP reset, network failure, or other unexpected problem.

Socket operations may raise exceptions such as:

- `ConnectionResetError` - the remote connection was forcibly closed or reset.
- `BrokenPipeError` - the server attempted to send data after the remote side had already closed the connection.
- `ConnectionAbortedError` - the connection was unexpectedly aborted.
- `TimeoutError` - a configured socket timeout expired because the remote side stopped responding.

The server must catch these exceptions so that one failed connection does not crash the entire server.

Example:

```python
try:
    data = sock.recv(4096)

    if not data:
        sock.close()
        handle_client_disconnect(player_id)

except (
    ConnectionResetError,
    BrokenPipeError,
    ConnectionAbortedError,
    TimeoutError
):
    handle_client_disconnect(player_id)
```

The disconnect handler then triggers the appropriate state-machine transition.

During a game:

```text
CLIENT_DISCONNECTED
        ↓
GAME_OVER
        ↓
CLEANUP
        ↓
WAITING_FOR_PLAYERS
```

The connected opponent wins by forfeit.

Before the game begins, the disconnected player is removed and the server remains in or returns to `WAITING_FOR_PLAYERS`.

---

## 7. Post-Game Reset

After any game ends, whether because all ships are sunk or because a player disconnects, the server performs cleanup before accepting another game.

The cleanup process includes:

1. Closing both current client sockets.
2. Removing Player 1 and Player 2 information.
3. Clearing both Battleship boards.
4. Clearing attack history.
5. Resetting the active player.
6. Resetting ship-placement information.
7. Returning the state machine to `WAITING_FOR_PLAYERS`.

The server process itself remains running so that two new clients can connect and start another game.
