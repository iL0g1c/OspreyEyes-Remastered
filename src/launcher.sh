#!/bin/bash

if [ -f .env ]; then
    source .env
else
    echo "No .env file found. Exiting."
    exit 1
fi

VENVPATH=../venv/bin/activate
BOT_SCRIPT_PATH="bot/MindsEye.py"
SERVER_LAYER_PATH="server/dataCollectionLayer.py"
MONGODB_URI="$MONGODB_URI"

gnome-terminal -- bash -c "source $VENVPATH; python $BOT_SCRIPT_PATH; exec bash"
gnome-terminal -- bash -c "source $VENVPATH; python $SERVER_LAYER_PATH; exec bash"
gnome-terminal -- bash -c "mongosh $MONGODB_URI; exec bash"