# Game State Machine Specification

## 1. Overview

This FSM shows the server-side flow of the two-player Battleship game. The server handles player connections, ship placement, turns, move validation, win detection, disconnects, and cleanup.

Player 1 is the first player to connect and takes the first turn after both players finish placing their ships.

---

## 2. Server State Diagram

```mermaid
stateDiagram-v2
    [*] --> INIT

    INIT --> WAITING_FOR_PLAYERS: Server starts and begins listening

    WAITING_FOR_PLAYERS --> WAITING_FOR_PLAYERS: First CONNECT / assign Player_1 and send LOBBY_WAIT
    WAITING_FOR_PLAYERS --> GAME_START: Second CONNECT / assign Player_2

    GAME_START --> SHIP_PLACEMENT: Send GAME_START to both players

    SHIP_PLACEMENT --> SHIP_PLACEMENT: Valid PLACE_SHIP, fleet incomplete / save placement and send STATE_UPDATE
    SHIP_PLACEMENT --> SHIP_PLACEMENT: Invalid PLACE_SHIP / send ERROR
    SHIP_PLACEMENT --> PLAYER_TURN: Both players placed all ships / set Player_1 active and send STATE_UPDATE

    PLAYER_TURN --> PLAYER_TURN: Invalid or out-of-turn MOVE / send ERROR
    PLAYER_TURN --> EVALUATE_MOVE: Valid MOVE

    EVALUATE_MOVE --> PLAYER_TURN: No winner / send MOVE_RESULT and STATE_UPDATE, switch active player
    EVALUATE_MOVE --> GAME_OVER: All opponent ships sunk / send MOVE_RESULT and GAME_OVER

    WAITING_FOR_PLAYERS --> WAITING_FOR_PLAYERS: Client disconnect, EOF, or socket error / remove client

    GAME_START --> GAME_OVER: DISCONNECT, EOF, or socket error / opponent wins by FORFEIT
    SHIP_PLACEMENT --> GAME_OVER: DISCONNECT, EOF, or socket error / opponent wins by FORFEIT
    PLAYER_TURN --> GAME_OVER: DISCONNECT, EOF, or socket error / opponent wins by FORFEIT
    EVALUATE_MOVE --> GAME_OVER: DISCONNECT, EOF, or socket error / opponent wins by FORFEIT

    GAME_OVER --> CLEANUP: Final result sent
    CLEANUP --> WAITING_FOR_PLAYERS: Close sockets and reset game state
```

---

## 3. State Descriptions

### INIT

The server initializes and starts listening for TCP connections, then moves to `WAITING_FOR_PLAYERS`.

### WAITING_FOR_PLAYERS

The first client is assigned `Player_1` and receives `LOBBY_WAIT`. The second client is assigned `Player_2`, and the server moves to `GAME_START`.

If a player disconnects before the game starts, that player is removed and the server continues waiting.

### GAME_START

The server sends `GAME_START` to both players and begins the ship-placement phase.

### SHIP_PLACEMENT

Each player places:

- Carrier: 5
- Battleship: 4
- Submarine: 3
- Destroyer: 2

A placement must stay inside the 10 x 10 board, not overlap another ship, and use a valid ship and orientation.

Invalid placements cause an `ERROR` and remain in `SHIP_PLACEMENT`.

Once both players place all four ships, Player 1 becomes active and the server moves to `PLAYER_TURN`.

### PLAYER_TURN

The server waits for a `MOVE` from the active player.

A move is invalid if it:

- Comes from the wrong player
- Uses coordinates outside 0-9
- Targets a coordinate already attacked
- Contains invalid or missing fields

Invalid moves send `ERROR` and remain in `PLAYER_TURN`.

Valid moves transition to `EVALUATE_MOVE`.

### EVALUATE_MOVE

The server determines whether the move is a `HIT`, `MISS`, or `SUNK` and sends `MOVE_RESULT`.

If the opponent still has ships remaining, the active player switches and the server returns to `PLAYER_TURN`.

If all opponent ships are sunk, the server sends `GAME_OVER`.

### GAME_OVER

The game ends when:

- All of one player's ships are sunk, or
- A player disconnects after the game has started.

The reason is either:

```text
ALL_SHIPS_SUNK
```

or:

```text
FORFEIT
```

The server then moves to `CLEANUP`.

### CLEANUP

The server closes the current client sockets and clears:

- Player information
- Boards
- Attack history
- Ship placement data
- Active player
- Current game phase

The server then returns to `WAITING_FOR_PLAYERS` for another game.

---

## 4. Disconnect Handling

A disconnect can be detected by:

- `DISCONNECT`
- TCP EOF (`b""`)
- `ConnectionResetError`
- `BrokenPipeError`
- `ConnectionAbortedError`
- `TimeoutError`

Before the game begins, the disconnected player is removed and the server remains in `WAITING_FOR_PLAYERS`.

After the game begins, the opponent wins by forfeit:

```text
Current Game State
        ↓
Client Disconnect
        ↓
GAME_OVER
        ↓
CLEANUP
        ↓
WAITING_FOR_PLAYERS
```

---

## 5. Normal Game Flow

```text
INIT
  ↓
WAITING_FOR_PLAYERS
  ↓
GAME_START
  ↓
SHIP_PLACEMENT
  ↓
PLAYER_TURN
  ↓
EVALUATE_MOVE
  ↓
PLAYER_TURN
  ↓
   ...
  ↓
GAME_OVER
  ↓
CLEANUP
  ↓
WAITING_FOR_PLAYERS
```

`PLAYER_TURN` and `EVALUATE_MOVE` repeat until one player wins or disconnects.