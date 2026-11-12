
"""Two-player TCP Battleship server"""

import argparse
import queue
import socket
import threading

from protocol import (
    BOARD_SIZE, MAX_MESSAGE_BYTES, SHIP_SIZES, ProtocolError,
    decode_frame, make_message, serialize_message,
)


def port_number(value):
    try:
        port = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Port must be a number (1024-65535).") from exc
    if not 1024 <= port <= 65535:
        raise argparse.ArgumentTypeError("Port must be between 1024 and 65535.")
    return port


class Player:
    """A registered TCP client and its private game state."""

    def __init__(self, player_id, alias, sock, server):
        self.player_id = player_id
        self.alias = alias
        self.sock = sock
        self.server = server
        self.active = True
        self.outgoing = queue.Queue()
        self.board = [["EMPTY" for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]
        self.ships = {}
        self.sender = threading.Thread(target=self._send_messages, daemon=True)
        self.sender.start()

    def _send_messages(self):
        """Send in FIFO order outside the shared game lock."""
        try:
            while True:
                message = self.outgoing.get()
                if message is None:
                    break
                self.sock.sendall(serialize_message(message))
        except OSError:
            self.server.handle_disconnect(self, "Connection lost while sending.")
        finally:
            try:
                self.sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self.sock.close()

    def stop_after_queued_messages(self):
        self.active = False
        self.outgoing.put(None)

    def remaining_ships(self):
        return sum(
            1 for squares in self.ships.values()
            if not all(self.board[r][c] == "SUNK" for r, c in squares)
        ) + (len(SHIP_SIZES) - len(self.ships))


class BattleshipServer:
    def __init__(self, port):
        self.port = port
        self.game_lock = threading.Lock()
        self.players = {}
        self.phase = "WAITING_FOR_PLAYERS"
        self.active_player = None

    def _send(self, player, kind, payload):
        """Called with game_lock held. Queue personalized messages in order."""
        if player.active:
            player.outgoing.put(make_message(kind, player.player_id, payload))

    def _error(self, player, code, message):
        self._send(player, "ERROR", {"code": code, "message": message})

    def _other(self, player):
        return self.players.get("Player_2" if player.player_id == "Player_1" else "Player_1")

    def _state_for(self, player):
        opponent = self._other(player)

        # Do not reveal enemy ships unless they have been hit or sunk.
        opponent_board = [
            [cell if cell in ("HIT", "MISS", "SUNK") else "UNKNOWN" for cell in row]
            for row in opponent.board
        ]

        return {
            "phase": self.phase,
            "active_player": self.active_player,
            "own_board": [row[:] for row in player.board],
            "opponent_board": opponent_board,
            "remaining_own_ships": player.remaining_ships(),
            "remaining_opponent_ships": opponent.remaining_ships(),
        }

    def _broadcast_state(self):
        for player in self.players.values():
            self._send(player, "STATE_UPDATE", self._state_for(player))

    def _finish_game(self, winner, reason, disconnected=None):
        """Queue GAME_OVER before closing old session; server stays listening."""
        for player in list(self.players.values()):
            if player is not disconnected:
                self._send(player, "GAME_OVER", {"winner": winner, "reason": reason})
        old_players = list(self.players.values())
        self.players = {}
        self.phase = "WAITING_FOR_PLAYERS"
        self.active_player = None
        for player in old_players:
            player.stop_after_queued_messages()
        print("[SERVER] GAME_OVER: {} ({}) | Waiting for new players.".format(winner, reason), flush=True)

    def handle_disconnect(self, player, reason):
        with self.game_lock:
            if not player.active:
                return
            print("[SERVER] {} disconnected: {}".format(player.player_id, reason), flush=True)
            if self.phase == "WAITING_FOR_PLAYERS":
                self.players.pop(player.player_id, None)
                player.stop_after_queued_messages()
            else:
                opponent = self._other(player)
                if opponent:
                    self._finish_game(opponent.player_id, "FORFEIT", disconnected=player)
                else:
                    self.players.pop(player.player_id, None)
                    player.stop_after_queued_messages()

    def _register(self, sock, message):
        """Assign ID by registration order, never from the client's claimed ID."""
        with self.game_lock:
            if len(self.players) == 2:
                return None, "FULL"
            alias = message["payload"]["alias"].strip()
            if len(alias) > 40:
                return None, "ALIAS_TOO_LONG"
            player_id = "Player_1" if "Player_1" not in self.players else "Player_2"
            player = Player(player_id, alias, sock, self)
            self.players[player_id] = player
            print("[SERVER] {} joined as {}".format(alias, player_id), flush=True)
            if len(self.players) == 1:
                self._send(player, "LOBBY_WAIT", {"message": "Waiting for Player 2 to connect."})
            else:
                self.phase = "SHIP_PLACEMENT"
                for current in self.players.values():
                    opponent = self._other(current)
                    self._send(current, "GAME_START", {
                        "opponent_alias": opponent.alias,
                        "board_size": BOARD_SIZE,
                        "phase": "SHIP_PLACEMENT",
                    })
                print("[SERVER] Both players connected. Ship placement started.", flush=True)
            return player, None

    def _place_ship(self, player, payload):
        if self.phase != "SHIP_PLACEMENT":
            self._error(player, "WRONG_PHASE", "Ship placement is not available now.")
            return

        ship = payload["ship"]
        if ship in player.ships:
            self._error(player, "DUPLICATE_SHIP", "You already placed that ship.")
            return

        row, col = payload["start_row"], payload["start_col"]
        horizontal = payload["orientation"] == "HORIZONTAL"
        cells = {
            (row + (0 if horizontal else step), col + (step if horizontal else 0))
            for step in range(SHIP_SIZES[ship])
        }

        if any(r >= BOARD_SIZE or c >= BOARD_SIZE for r, c in cells):
            self._error(player, "OUT_OF_BOUNDS", "That ship extends outside the board.")
            return

        if any(player.board[r][c] != "EMPTY" for r, c in cells):
            self._error(player, "SHIP_OVERLAP", "That ship overlaps another ship.")
            return

        for r, c in cells:
            player.board[r][c] = "SHIP"
        player.ships[ship] = cells
        print("[SERVER] {} placed {}".format(player.player_id, ship), flush=True)

        # Only the placing player needs an interim update.
        self._send(player, "STATE_UPDATE", self._state_for(player))

        if all(len(p.ships) == len(SHIP_SIZES) for p in self.players.values()):
            self.phase = "BATTLE"
            self.active_player = "Player_1"
            self._broadcast_state()
            print("[SERVER] Both fleets placed. Player_1's turn.", flush=True)

    def _move(self, player, payload):
        if self.phase != "BATTLE":
            self._error(player, "WRONG_PHASE", "Finish ship placement before attacking.")
            return

        if player.player_id != self.active_player:
            self._error(player, "OUT_OF_TURN", "It is not your turn.")
            return

        opponent = self._other(player)
        row, col = payload["row"], payload["col"]
        square = opponent.board[row][col]

        # Previously attacked squares cannot be attacked again.
        if square in ("HIT", "MISS", "SUNK"):
            self._error(player, "REPEATED_ATTACK", "You already attacked this coordinate.")
            return

        hit_ship = next(
            (name for name, squares in opponent.ships.items() if (row, col) in squares), None
        )

        if hit_ship is None:
            opponent.board[row][col] = "MISS"
            result = "MISS"
        else:
            opponent.board[row][col] = "HIT"

            sunk = all(
                opponent.board[r][c] == "HIT"
                for r, c in opponent.ships[hit_ship]
            )

            if sunk:
                # Mark every square of the sunk ship.
                for r, c in opponent.ships[hit_ship]:
                    opponent.board[r][c] = "SUNK"

            result = "SUNK" if sunk else "HIT"

        print("[SERVER] {} attacked ({}, {}): {}".format(
            player.player_id, row, col, result), flush=True)

        outcome = {"row": row, "col": col, "result": result, "ship": hit_ship}

        for current in self.players.values():
            self._send(current, "MOVE_RESULT", outcome)

        if opponent.remaining_ships() == 0:
            self._broadcast_state()
            self._finish_game(player.player_id, "ALL_SHIPS_SUNK")
        else:
            self.active_player = opponent.player_id
            self._broadcast_state()
            print("[SERVER] Next turn: {}".format(self.active_player), flush=True)

    def _process(self, player, message):
        with self.game_lock:
            if not player.active:
                return
            if message["player_id"] != player.player_id:
                self._error(player, "INVALID_PLAYER", "Player ID does not match this connection.")
                return

            kind = message["msg_type"]
            if kind == "PLACE_SHIP":
                self._place_ship(player, message["payload"])
            elif kind == "MOVE":
                self._move(player, message["payload"])
            elif kind == "DISCONNECT":
                # Handle outside the lock to avoid acquiring the same lock twice.
                pass
            else:
                self._error(player, "INVALID_REQUEST", "Unexpected message type from client.")

        if message["msg_type"] == "DISCONNECT":
            self.handle_disconnect(player, message["payload"]["reason"])

    @staticmethod
    def _reject_unregistered(sock, code, description):
        try:
            sock.sendall(serialize_message(make_message(
                "ERROR", None, {"code": code, "message": description}
            )))
        except OSError:
            pass

    def _client_worker(self, sock, address):
        player = None
        buffer = b""

        try:
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break

                buffer += chunk

                if len(buffer) > MAX_MESSAGE_BYTES + 4096 and b"\n" not in buffer:
                    raise ProtocolError("Message exceeds maximum size.")

                while b"\n" in buffer:
                    frame, buffer = buffer.split(b"\n", 1)

                    try:
                        message = decode_frame(frame)
                    except ProtocolError as exc:
                        if player:
                            with self.game_lock:
                                self._error(player, "BAD_MESSAGE", str(exc))
                        else:
                            self._reject_unregistered(sock, "BAD_MESSAGE", str(exc))
                        continue

                    if player is None:
                        if message["msg_type"] != "CONNECT" or message["player_id"] is not None:
                            self._reject_unregistered(
                                sock, "CONNECT_REQUIRED",
                                "Send CONNECT with a null player_id first."
                            )
                            continue

                        player, error = self._register(sock, message)
                        if error:
                            self._reject_unregistered(
                                sock, error, "Game is full or alias is too long."
                            )
                            return
                    else:
                        self._process(player, message)

                    if player and not player.active:
                        return

        except (OSError, ProtocolError) as exc:
            if player:
                self.handle_disconnect(player, str(exc))
            else:
                self._reject_unregistered(sock, "CONNECTION_ERROR", str(exc))
        finally:
            if player:
                self.handle_disconnect(player, "Connection closed (TCP EOF).")
            else:
                sock.close()

    def serve_forever(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(("0.0.0.0", self.port))
            listener.listen()
            print("[SERVER] Listening on 0.0.0.0:{} (TCP)".format(self.port), flush=True)

            try:
                while True:
                    sock, address = listener.accept()
                    worker = threading.Thread(
                        target=self._client_worker, args=(sock, address), daemon=True
                    )
                    worker.start()
            except KeyboardInterrupt:
                print("\n[SERVER] Stopped.", flush=True)


def main():
    parser = argparse.ArgumentParser(description="Two-player TCP Battleship server")
    parser.add_argument("-p", "--port", required=True, type=port_number,
                        help="TCP port to listen on (1024-65535)")
    args = parser.parse_args()

    try:
        BattleshipServer(args.port).serve_forever()
    except OSError as exc:
        parser.exit(1, "[ERROR] Could not start server: {}\n".format(exc))


if __name__ == "__main__":
    main()
