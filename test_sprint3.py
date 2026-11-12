"""Unittest coverage for Sprint 3 protocol and real localhost TCP sessions."""

import json
import pathlib
import socket
import subprocess
import sys
import time
import unittest

from protocol import (
    ProtocolError, make_message, parse_received_data, serialize_message,
)

ROOT = pathlib.Path(__file__).resolve().parent
FLEET_A = [("Carrier", 0, 0, "HORIZONTAL"),
           ("Battleship", 1, 0, "HORIZONTAL"),
           ("Submarine", 2, 0, "HORIZONTAL"),
           ("Destroyer", 3, 0, "HORIZONTAL")]
FLEET_B = [("Carrier", 0, 0, "HORIZONTAL"),
           ("Battleship", 1, 0, "HORIZONTAL"),
           ("Submarine", 2, 0, "HORIZONTAL"),
           ("Destroyer", 3, 0, "HORIZONTAL")]


class TestProtocol(unittest.TestCase):
    def test_fragmented_and_multiple_tcp_frames(self):
        first = serialize_message(make_message("MOVE", "Player_1", {"row": 2, "col": 4}))
        second = serialize_message(make_message("MOVE", "Player_2", {"row": 5, "col": 7}))
        messages, remainder = parse_received_data(b"", first[:12])
        self.assertEqual(messages, [])
        messages, remainder = parse_received_data(remainder, first[12:] + second + first[:4])
        self.assertEqual([m["player_id"] for m in messages], ["Player_1", "Player_2"])
        self.assertEqual(remainder, first[:4])

    def test_invalid_messages_rejected(self):
        bad = [
            b'not json\n',
            b'{"msg_type":"SUPER_ATTACK","player_id":null,"payload":{},"timestamp":1}\n',
            b'{"msg_type":"MOVE","player_id":"Player_1","payload":{"row":11,"col":2},"timestamp":1}\n',
            b'{"msg_type":"CONNECT","player_id":[],"payload":{"alias":"A"},"timestamp":1}\n',
            b'{"msg_type":"GAME_OVER","player_id":null,"payload":{"winner":[],"reason":"FORFEIT"},"timestamp":1}\n',
            b'\xff\n',
        ]
        for data in bad:
            with self.subTest(data=data), self.assertRaises(ProtocolError):
                parse_received_data(b"", data)


class Peer:
    def __init__(self, port):
        self.sock = socket.create_connection(("127.0.0.1", port), timeout=3)
        self.sock.settimeout(3)
        self.f = self.sock.makefile("rb")
        self.player_id = None

    def send(self, kind, payload, player_id=None, fragment=False):
        who = self.player_id if player_id is None else player_id
        data = serialize_message(make_message(kind, who, payload))
        if fragment:
            self.sock.sendall(data[:9]); self.sock.sendall(data[9:])
        else:
            self.sock.sendall(data)

    def get(self, expected):
        raw = self.f.readline()
        if not raw:
            raise AssertionError("Expected {}, got connection close".format(expected))
        item = json.loads(raw)
        assert item["msg_type"] == expected, "Expected {}, got {}".format(expected, item)
        return item

    def close(self):
        try:
            self.f.close()
        except OSError:
            pass
        self.sock.close()


class TestSession(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            cls.port = probe.getsockname()[1]
        cls.server = subprocess.Popen(
            [sys.executable, "-u", str(ROOT / "server.py"), "-p", str(cls.port)],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            cwd=str(ROOT),
        )
        # Give the server time to start before connecting.
        for _ in range(20):
            # Check whether the server crashed during startup.
            if cls.server.poll() is not None:
                error = cls.server.stderr.read().decode(errors="replace")
                raise AssertionError(f"Server exited during startup:\n{error}")

            try:
                probe_sock = socket.create_connection(
                    ("127.0.0.1", cls.port), timeout=1.0
                )
                probe_sock.close()
                break
            except OSError:
                time.sleep(0.1)
        else:
            cls.server.terminate()
            raise AssertionError("Server failed to accept connections.")

    @classmethod
    def tearDownClass(cls):
        cls.server.terminate()
        try:
            cls.server.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            cls.server.kill()

    def _connect_two(self):
        a = Peer(self.port)
        a.send("CONNECT", {"alias": "Adnan"}, fragment=True)
        a.player_id = a.get("LOBBY_WAIT")["player_id"]
        self.assertEqual(a.player_id, "Player_1")
        b = Peer(self.port)
        b.send("CONNECT", {"alias": "Judy"})
        a.get("GAME_START")
        b.player_id = b.get("GAME_START")["player_id"]
        self.assertEqual(b.player_id, "Player_2")
        return a, b

    def _place_fleets(self, a, b):
        for peer, fleet in ((a, FLEET_A), (b, FLEET_B)):
            for name, row, col, orient in fleet:
                peer.send("PLACE_SHIP", {
                    "ship": name, "start_row": row, "start_col": col, "orientation": orient
                })
                current = peer.get("STATE_UPDATE")
                self.assertEqual(current["payload"]["phase"], "SHIP_PLACEMENT")
        for peer in (a, b):
            current = peer.get("STATE_UPDATE")
            self.assertEqual(current["payload"]["phase"], "BATTLE")
            self.assertEqual(current["payload"]["active_player"], "Player_1")
        return a, b

    def _attack(self, attacker, defender, row, col, result, next_player):
        attacker.send("MOVE", {"row": row, "col": col})
        for peer in (attacker, defender):
            outcome = peer.get("MOVE_RESULT")
            self.assertEqual(outcome["payload"]["result"], result)
            state = peer.get("STATE_UPDATE")
            self.assertEqual(state["payload"]["active_player"], next_player)
            self.assertNotIn("SHIP", set(cell for line in state["payload"]["opponent_board"] for cell in line))

    def test_multi_turn_errors_forfeit_and_reset(self):
        a, b = self._connect_two()
        try:
            self._place_fleets(a, b)
            third = Peer(self.port)
            third.send("CONNECT", {"alias": "Third"})
            self.assertEqual(third.get("ERROR")["payload"]["code"], "FULL")
            third.close()

            # Client 2 cannot attack first; the turn stays with Client 1.
            b.send("MOVE", {"row": 9, "col": 9})
            self.assertEqual(b.get("ERROR")["payload"]["code"], "OUT_OF_TURN")
            self._attack(a, b, 0, 0, "HIT", "Player_2")
            self._attack(b, a, 9, 9, "MISS", "Player_1")
            a.send("MOVE", {"row": 0, "col": 0})
            self.assertEqual(a.get("ERROR")["payload"]["code"], "REPEATED_ATTACK")
            self._attack(a, b, 0, 1, "HIT", "Player_2")

            b.send("DISCONNECT", {"reason": "Leaving."})
            winner = a.get("GAME_OVER")
            self.assertEqual(winner["payload"], {"winner": "Player_1", "reason": "FORFEIT"})
        finally:
            a.close(); b.close()
        # After cleanup, a new pair can start without restarting the server.
        c, d = self._connect_two()
        c.close()
        winner = d.get("GAME_OVER")
        self.assertEqual(winner["payload"]["reason"], "FORFEIT")
        d.close()

    def test_sunk_and_normal_game_over(self):
        a, b = self._connect_two()
        try:
            self._place_fleets(a, b)
            # P1 attacks every ship square; P2 shoots empty squares in between.
            target_cells = ([(0, i) for i in range(5)] + [(1, i) for i in range(4)]
                            + [(2, i) for i in range(3)] + [(3, i) for i in range(2)])
            for index, (row, col) in enumerate(target_cells):
                a.send("MOVE", {"row": row, "col": col})
                result_a = a.get("MOVE_RESULT")
                b.get("MOVE_RESULT")
                self.assertEqual(result_a["payload"]["result"],
                                 "SUNK" if index in (4, 8, 11, 13) else "HIT")
                current_a = a.get("STATE_UPDATE")
                current_b = b.get("STATE_UPDATE")
                self.assertNotIn("SHIP", set(c for line in current_a["payload"]["opponent_board"] for c in line))
                if index == len(target_cells) - 1:
                    self.assertEqual(current_a["payload"]["remaining_opponent_ships"], 0)
                    self.assertEqual(a.get("GAME_OVER")["payload"], {
                        "winner": "Player_1", "reason": "ALL_SHIPS_SUNK"
                    })
                    b.get("GAME_OVER")
                    break
                b.send("MOVE", {"row": 9 - index // 10, "col": index % 10})
                a.get("MOVE_RESULT"); b.get("MOVE_RESULT")
                a.get("STATE_UPDATE"); b.get("STATE_UPDATE")
        finally:
            a.close(); b.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
