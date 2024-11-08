#!/bin/bash

SESSION_NAME="OspreyEyes-Session"
LOGS_DIR="../../logs"

# Kill any existing session with the same name
tmux kill-session -t $SESSION_NAME 2>/dev/null

# Start a new tmux session and run the first tail command in pane 0
tmux new-session -d -s $SESSION_NAME -n 'Logs' "echo 'Teleportation Events'; tail -f $LOGS_DIR/teleportation.log"

# Split pane 0 vertically to create pane 1 and run the second tail command
tmux split-window -v -t $SESSION_NAME:0.0 "echo 'Aircraft Change Events'; tail -f $LOGS_DIR/aircraft-change.log"

# Split pane 0 horizontally to create pane 2 and run the third tail command
tmux split-window -h -t $SESSION_NAME:0.0 "echo 'Callsign Change Events'; tail -f $LOGS_DIR/callsign-change.log"

# Split pane 1 horizontally to create pane 3 and run the fourth tail command
tmux split-window -h -t $SESSION_NAME:0.1 "echo 'New Account Events'; tail -f $LOGS_DIR/new-account.log"

# Split pane 2 vertically to create pane 4 and run the fifth tail command
tmux split-window -v -t $SESSION_NAME:0.2 "echo 'Offline Online Events'; tail -f $LOGS_DIR/offline-online.log"

# Split pane 3 vertically to create pane 5 and run the sixth tail command
tmux split-window -v -t $SESSION_NAME:0.3 "echo 'Server Events'; tail -f $LOGS_DIR/server-events.log"

# Arrange panes in a tiled layout
tmux select-layout -t $SESSION_NAME tiled

# Attach to the tmux session
tmux attach-session -t $SESSION_NAME
