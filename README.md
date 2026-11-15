# CS 457 Term Project - Battleship
# By: Adnan Alturkestani

## Overview
This project is a two-player networked Battleship game created for CS 457. The game will run in the command line and allow two players on separate client nodes to connect to a game server.

## Description
Players take turns choosing coordinates to attack the opponent's board. The server keeps track of the game state and tells each player whether their attack was a hit or miss. The game ends when one player sinks all of the opponent's ships.

## Running the Game

This project uses Python 3 and the standard library. No additional packages are required.

Open three terminals in the project directory.

**Server:**
```bash
python server.py -p 8080
```

**Player 1:**
```bash
python client.py -i localhost -p 8080
```

**Player 2:**
```bash
python client.py -i localhost -p 8080
```

Each player enters a name, places four ships, and takes turns attacking the opponent's board.

## Running Tests

```bash
python -m unittest -v test_sprint3.py
```

The tests cover TCP message framing, protocol validation, multiplayer gameplay, turn enforcement, disconnects, and game completion.

## DNS Support

The client accepts a DNS hostname or IP address through `-i` and handles DNS resolution failures gracefully. The custom CML DNS setup will be completed in Sprint 4.
