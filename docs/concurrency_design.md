
# Sprint 2: Server Concurrency Design

**Course:** CS 457 Computer Networks  
**Game:** Two-Player Battleship  
**Student:** Adnan Alturkestani

## 1. Server Concurrency Architecture

The Battleship server will use Python's `threading.Thread` to handle both players at the same time. Each player will have a separate worker thread to receive messages, so one player does not block the other or stop the server from accepting connections.

The server manages the game boards, player turns, scores, and connected clients. The main thread listens for connections, while the worker threads handle client messages. Each client will also have an outgoing message queue and sender thread to deliver updates in order.

Since both players share the same game information, `threading.Lock` will be used to prevent race conditions.

The game will continue using TCP, JSON, UTF-8, and newline-delimited messages from Sprint 1.

## 2. Connection Lifecycle

The server will handle connections as follows:

1. **Listening:** The server creates a TCP socket using `bind()` and `listen()`.
2. **Connecting:** The main thread accepts connections using `accept()`. After sending `CONNECT`, the first player becomes `Player_1` and receives `LOBBY_WAIT`.
3. **Game start:** Once the second player connects and registers as `Player_2`, the server sends `GAME_START` to both clients.
4. **Gameplay:** Each player's worker thread handles incoming messages while the server manages ship placements, turns, and moves.
5. **Game over:** The server sends `GAME_OVER`, closes both sockets, resets the game information, and waits for new players.

Only two players are allowed per game. A third connection will be rejected with an `ERROR` message.

If a player disconnects before the game starts, the server continues waiting. If someone disconnects during the game, the other player wins by forfeit. Disconnects are detected through `DISCONNECT`, TCP EOF (`recv()` returning `b""`), or socket errors.

## 3. Thread Safety and Locking

Both worker threads need access to the same game information. Without locking, they could update it at the same time and cause incorrect results.

The shared information includes:

- Both game boards and ship placements.
- Active player and game phase.
- Previous attacks, remaining ships, and scores.
- Connected client information.

The server will use `with game_lock:` when reading or changing shared information.

When a player sends a `MOVE`, the worker thread:

1. Acquires `game_lock`.
2. Checks the player's turn and whether the move is valid.
3. Updates the board, score, and active turn if the move is valid.
4. Adds the results and state updates to both players' message queues.
5. Releases the lock.

Only one thread can update the game state at a time. This prevents issues such as both players making moves simultaneously or the active turn changing incorrectly.

Socket sending happens outside the lock, so a slow connection does not hold up the game.

## 4. Turn Enforcement and Move Validation

The server checks every `MOVE` before accepting it. A move is only valid if:

- The game is in the `BATTLE` phase.
- It is the player's turn.
- The coordinates are between 0 and 9.
- The location has not already been attacked.

The server identifies players using their registered connections rather than trusting the `player_id` inside a message.

Invalid or out-of-turn moves receive an `ERROR` and do not change the game state.

For a valid move, the server checks whether it is a `HIT`, `MISS`, or `SUNK`, sends `MOVE_RESULT` to both clients, and switches turns unless the game is over.

## 5. State and Score Synchronization

After every valid ship placement or move, the server sends a personalized `STATE_UPDATE` to both clients. Each update includes:

- Current game phase and active player.
- The player's own board.
- Known hits and misses on the opponent's board.
- Remaining ships for both players.

The server never reveals the locations of unhit enemy ships.

Each player earns one point for every enemy ship sunk. Since there are four ships per player, scores range from 0 to 4.

Scores can be calculated from the existing protocol:

- My score = `4 - remaining_opponent_ships`
- Opponent's score = `4 - remaining_own_ships`

The server queues updates for both players while holding the lock, keeping their game information consistent. The messages are then sent in order, although network delays may cause one client to receive them slightly later.

When all of a player's ships are sunk, the server sends `GAME_OVER` and resets the game for the next two players.

