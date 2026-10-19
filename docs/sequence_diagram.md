
# Sprint 2: Sequence Diagram

**Architecture:** Multi-threading with `threading.Lock`

## 1. Mermaid Sequence Diagram

The diagram shows how both players communicate with the server, from connecting and placing ships to taking turns and finishing the game.

```mermaid
sequenceDiagram
    autonumber
    actor P1 as Player 1
    participant S as Server
    actor P2 as Player 2

    P1->>S: CONNECT
    S-->>P1: LOBBY_WAIT
    P2->>S: CONNECT
    S-->>P1: GAME_START
    S-->>P2: GAME_START

    par Player 1 places ships
        loop Until 4 ships are placed
            P1->>S: PLACE_SHIP
            S-->>P1: STATE_UPDATE
            S-->>P2: STATE_UPDATE
        end
    and Player 2 places ships
        loop Until 4 ships are placed
            P2->>S: PLACE_SHIP
            S-->>P1: STATE_UPDATE
            S-->>P2: STATE_UPDATE
        end
    end

    Note over S: Both fleets ready, Player 1 goes first
    S-->>P1: STATE_UPDATE (BATTLE, Player 1 turn)
    S-->>P2: STATE_UPDATE (BATTLE, Player 1 turn)

    P2->>S: MOVE (out of turn)
    S-->>P2: ERROR (OUT_OF_TURN)
    Note over S: Turn stays with Player 1

    P1->>S: MOVE
    Note over S: Lock game state and validate move

    alt Invalid or repeated move
        S-->>P1: ERROR
        Note over S: No changes to game state
    else Valid move
        Note over S: Update board and switch turn
        S-->>P1: MOVE_RESULT
        S-->>P2: MOVE_RESULT
        S-->>P1: STATE_UPDATE
        S-->>P2: STATE_UPDATE
    end

    P2->>S: MOVE
    Note over S: Lock, validate and update game state

    alt Game continues
        S-->>P1: MOVE_RESULT
        S-->>P2: MOVE_RESULT
        Note over S: Switch turn back to Player 1
        S-->>P1: STATE_UPDATE
        S-->>P2: STATE_UPDATE
    else Final ship sunk
        S-->>P1: MOVE_RESULT
        S-->>P2: MOVE_RESULT
        S-->>P1: STATE_UPDATE
        S-->>P2: STATE_UPDATE
        S-->>P1: GAME_OVER
        S-->>P2: GAME_OVER
        Note over S: Close sockets and reset game
    end
```

## 2. State and Score Synchronization

The server controls the game state and uses `threading.Lock` when checking moves or updating shared information. This prevents both player threads from changing the game at the same time.

- **Valid moves:** The server updates the board, sends `MOVE_RESULT`, and broadcasts `STATE_UPDATE` to both players.
- **Invalid moves:** The server sends `ERROR` without changing the turn, board, or score.
- **State updates:** Each player receives their own board and known opponent hits and misses without revealing hidden ships.
- **Scores:** Players earn one point for each enemy ship sunk. Scores are calculated from the remaining ship counts in `STATE_UPDATE`.
- **Game over:** The server sends `GAME_OVER`, closes both game connections, and resets for the next game.

Messages are placed in each client's outgoing queue while the game state is locked. The sender threads then deliver them in order without holding the lock.

If a player disconnects during the game, the remaining player wins by forfeit. If a third client connects while the game is full, the server rejects the connection.
