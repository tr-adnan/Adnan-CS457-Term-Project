
"""Console Battleship client"""

import argparse
import queue
import socket
import threading
import sys

from protocol import (
    MAX_MESSAGE_BYTES, SHIP_SIZES, ProtocolError, decode_frame,
    make_message, serialize_message,
)


SYMBOLS = {
    "EMPTY": ".",
    "SHIP": "S",
    "HIT": "X",
    "SUNK": "-",
    "MISS": "o",
    "UNKNOWN": "?"
}


def port_number(value):
    try:
        port = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Port must be a number (1024-65535).") from exc
    if not 1024 <= port <= 65535:
        raise argparse.ArgumentTypeError("Port must be between 1024 and 65535.")
    return port


def display_board(board, title):
    print("\n{}".format(title))
    print("    " + " ".join(str(i) for i in range(10)))
    for row_number, row in enumerate(board):
        print(" {:2} ".format(row_number) + " ".join(SYMBOLS[cell] for cell in row))


class BattleshipClient:
    def __init__(self, sock, alias):
        self.sock = sock
        self.alias = alias
        self.player_id = None
        self.events = queue.Queue()
        self.ship_names = list(SHIP_SIZES)
        self.next_ship = 0
        self.pending_ship = None
        self.pending_move = False
        self.phase = None
        self.active_player = None
        self.sock_closed = False

    def send(self, kind, payload):
        self.sock.sendall(serialize_message(make_message(kind, self.player_id, payload)))

    def receive_loop(self):
        """A receiver thread keeps reading while the user is typing."""
        buffer = b""
        try:
            while True:
                chunk = self.sock.recv(4096)
                if not chunk:
                    break
                buffer += chunk
                if len(buffer) > MAX_MESSAGE_BYTES + 4096 and b"\n" not in buffer:
                    raise ProtocolError("Server sent an oversized message.")
                while b"\n" in buffer:
                    frame, buffer = buffer.split(b"\n", 1)
                    self.events.put(decode_frame(frame))
        except (OSError, ProtocolError) as exc:
            self.events.put(("ERROR", str(exc)))
        finally:
            self.events.put(None)

    def prompt_ship(self):
        name = self.ship_names[self.next_ship]
        while True:
            raw = input("Place {} (size {}) - row col H/V: ".format(name, SHIP_SIZES[name]))
            parts = raw.strip().split()
            if len(parts) != 3:
                print("Enter three values, e.g. 0 0 H")
                continue
            try:
                row, col = int(parts[0]), int(parts[1])
            except ValueError:
                print("Rows and columns must be numbers from 0 to 9.")
                continue
            orientation = {"H": "HORIZONTAL", "V": "VERTICAL"}.get(parts[2].upper())
            if not (0 <= row <= 9 and 0 <= col <= 9 and orientation):
                print("Use row/col 0-9 and H (horizontal) or V (vertical).")
                continue
            self.pending_ship = name
            self.send("PLACE_SHIP", {
                "ship": name, "start_row": row, "start_col": col,
                "orientation": orientation,
            })
            return

    def prompt_move(self):
        while True:
            raw = input("Your turn - attack row col (e.g. 2 4): ")
            parts = raw.strip().split()
            if len(parts) != 2:
                print("Enter two numbers, e.g. 2 4")
                continue
            try:
                row, col = int(parts[0]), int(parts[1])
            except ValueError:
                print("Rows and columns must be numbers from 0 to 9.")
                continue
            if not (0 <= row <= 9 and 0 <= col <= 9):
                print("Rows and columns must be from 0 to 9.")
                continue
            self.pending_move = True
            self.send("MOVE", {"row": row, "col": col})
            return

    def show_state(self, payload):
        self.phase = payload["phase"]
        self.active_player = payload["active_player"]

        display_board(
            payload["own_board"],
            "YOUR BOARD  (S=ship, X=hit, -=sunk, o=miss, .=empty)"
        )

        if self.phase == "BATTLE":
            display_board(
                payload["opponent_board"],
                "OPPONENT BOARD  (?=unknown, X=hit, -=sunk, o=miss)"
            )

        your_score = 4 - payload["remaining_opponent_ships"]
        opponent_score = 4 - payload["remaining_own_ships"]
        print("Score: You {} - Opponent {}".format(your_score, opponent_score))

        if self.phase == "SHIP_PLACEMENT":
            if self.pending_ship:
                print("{} placed successfully.".format(self.pending_ship))
                self.next_ship += 1
                self.pending_ship = None
            if self.next_ship < len(self.ship_names):
                self.prompt_ship()
            else:
                print("All four ships placed. Waiting for opponent...")
        elif self.phase == "BATTLE":
            self.pending_ship = None

            # Don't ask for another attack if all ships are sunk.
            if payload["remaining_own_ships"] == 0 or payload["remaining_opponent_ships"] == 0:
                print("All ships sunk. Waiting for final result...")
            elif self.active_player == self.player_id and not self.pending_move:
                print("Your turn!")
                self.prompt_move()
            elif self.active_player != self.player_id:
                print("Waiting for {}...".format(self.active_player))

    def run(self):
        receiver = threading.Thread(target=self.receive_loop, daemon=True)
        receiver.start()
        self.send("CONNECT", {"alias": self.alias})
        try:
            while True:
                message = self.events.get()
                if message is None:
                    print("Connection to server closed.")
                    return
                if isinstance(message, tuple):
                    print("[ERROR] {}".format(message[1]))
                    return
                kind = message["msg_type"]
                payload = message["payload"]
                if kind == "LOBBY_WAIT":
                    self.player_id = message["player_id"]
                    print("Connected as {}. {}".format(self.player_id, payload["message"]))
                elif kind == "GAME_START":
                    self.player_id = message["player_id"]
                    print("\nGAME START! You are {} vs. {}.".format(
                        self.player_id, payload["opponent_alias"]
                    ))
                    print("Place four ships on the 10x10 grid. Coordinates are 0-9.")

                    # Show the empty board before the first ship placement.
                    empty_board = [["EMPTY"] * 10 for _ in range(10)]
                    display_board(
                        empty_board,
                        "YOUR BOARD  (S=ship, X=hit, -=sunk, o=miss, .=empty)"
                    )

                    self.prompt_ship()
                elif kind == "STATE_UPDATE":
                    self.show_state(payload)
                elif kind == "MOVE_RESULT":
                    who = "Your" if self.pending_move else "Opponent's"
                    ship = " ({})".format(payload["ship"]) if payload["ship"] else ""
                    print("\n{} attack at ({}, {}): {}{}".format(
                        who, payload["row"], payload["col"], payload["result"], ship
                    ))
                    self.pending_move = False
                elif kind == "ERROR":
                    print("[ERROR] {}: {}".format(payload["code"], payload["message"]))
                    if self.pending_ship:
                        self.pending_ship = None
                        self.prompt_ship()
                    elif self.pending_move:
                        self.pending_move = False
                        self.prompt_move()
                    elif self.player_id is None:
                        return
                elif kind == "GAME_OVER":
                    print("\nGAME OVER! {}".format(
                        "You win!" if payload["winner"] == self.player_id else "You lose."
                    ))
                    print("Winner: {} | Reason: {}".format(payload["winner"], payload["reason"]))
                    return
                elif kind == "DISCONNECT":
                    print("Disconnected: {}".format(payload["reason"]))
                    return
        except (KeyboardInterrupt, EOFError):
            print("\nLeaving game.")
            try:
                self.send("DISCONNECT", {"reason": "Player quit the game."})
            except OSError:
                pass
        finally:
            try:
                self.sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self.sock.close()


def main():
    parser = argparse.ArgumentParser(description="Two-player TCP Battleship console client")
    parser.add_argument("-i", "--hostname", required=True,
                        help="Server DNS name or IPv4 address (e.g. server.alturkestani.edu)")
    parser.add_argument("-p", "--port", type=port_number, required=True,
                        help="Server TCP port (1024-65535)")
    args = parser.parse_args()

    try:
        server_ip = socket.gethostbyname(args.hostname)
    except socket.gaierror as e:
        print(f"[ERROR] Unable to resolve DNS hostname '{args.hostname}'.")
        print("Please check your Cisco router DNS configuration ('ip dns server' / 'ip host') or verify domain spelling.")
        sys.exit(1)

    try:
        alias = input("Enter your player name: ").strip() or "Player"
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(10)
            sock.connect((server_ip, args.port))
            sock.settimeout(None)
            print("Connected to {} ({}) on port {}.".format(args.hostname, server_ip, args.port))
            BattleshipClient(sock, alias).run()
    except (OSError, TimeoutError) as exc:
        parser.exit(1, "[ERROR] Unable to connect to the server: {}\n".format(exc))
    except (KeyboardInterrupt, EOFError):
        print("\nCanceled.")


if __name__ == "__main__":
    main()
