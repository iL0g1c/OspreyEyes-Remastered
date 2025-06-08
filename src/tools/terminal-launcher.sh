#!/bin/bash

SESSION_NAME="OspreyEyes-Session"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOGS_DIR="$SCRIPT_DIR/../../logs"

# Kill any existing session with the same name
tmux kill-session -t $SESSION_NAME 2>/dev/null

#---------------------------
# Window 0: Multi-pane view
#---------------------------
# Start new session with first log and build split layout
 tmux new-session -d -s "$SESSION_NAME" -n 'All' \
  "echo 'Teleportation Events'; tail -f \"$LOGS_DIR\"/teleportation.log"
 tmux split-window -v -t "$SESSION_NAME":0.0 \
  "echo 'Aircraft Change Events'; tail -f \"$LOGS_DIR\"/aircraft-change.log"
 tmux split-window -h -t "$SESSION_NAME":0.0 \
  "echo 'Callsign Change Events'; tail -f \"$LOGS_DIR\"/callsign-change.log"
 tmux split-window -h -t "$SESSION_NAME":0.1 \
  "echo 'New Account Events'; tail -f \"$LOGS_DIR\"/new-account.log"
 tmux split-window -v -t "$SESSION_NAME":0.2 \
  "echo 'Offline Online Events'; tail -f \"$LOGS_DIR\"/offline-online.log"
 tmux split-window -v -t "$SESSION_NAME":0.3 \
  "echo 'Server Events'; tail -f \"$LOGS_DIR\"/server-events.log"
 tmux select-layout -t "$SESSION_NAME" tiled
 tmux select-pane -t "$SESSION_NAME":0.0

#-----------------------------------
# Windows 1..6: individual log view
#-----------------------------------
 tmux new-window -t "$SESSION_NAME" -n 'Teleportation' \
  "echo 'Teleportation Events'; tail -f \"$LOGS_DIR\"/teleportation.log"
 tmux new-window -t "$SESSION_NAME" -n 'AircraftChange' \
  "echo 'Aircraft Change Events'; tail -f \"$LOGS_DIR\"/aircraft-change.log"
 tmux new-window -t "$SESSION_NAME" -n 'CallsignChange' \
  "echo 'Callsign Change Events'; tail -f \"$LOGS_DIR\"/callsign-change.log"
 tmux new-window -t "$SESSION_NAME" -n 'NewAccount' \
  "echo 'New Account Events'; tail -f \"$LOGS_DIR\"/new-account.log"
 tmux new-window -t "$SESSION_NAME" -n 'OfflineOnline' \
  "echo 'Offline Online Events'; tail -f \"$LOGS_DIR\"/offline-online.log"
 tmux new-window -t "$SESSION_NAME" -n 'ServerEvents' \
  "echo 'Server Events'; tail -f \"$LOGS_DIR\"/server-events.log"

#-----------------------------------
# Key bindings for quick switching
#-----------------------------------
 tmux bind-key -n F1 select-window -t 0  # All
 tmux bind-key -n F2 select-window -t 1  # Teleportation
 tmux bind-key -n F3 select-window -t 2  # AircraftChange
 tmux bind-key -n F4 select-window -t 3  # CallsignChange
 tmux bind-key -n F5 select-window -t 4  # NewAccount
 tmux bind-key -n F6 select-window -t 5  # OfflineOnline
 tmux bind-key -n F7 select-window -t 6  # ServerEvents
 tmux bind-key -n F8 kill-session        # Quit

 tmux attach-session -t "$SESSION_NAME"