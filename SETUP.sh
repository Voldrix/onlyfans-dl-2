#!/bin/bash

# Prompt for user input and update user_config.py
read -p "Enter USER_ID: " USER_ID
read -p "Enter USER_AGENT: " USER_AGENT
read -p "Enter X_BC: " X_BC
read -p "Enter SESS_COOKIE: " SESS_COOKIE
read -p "Enter TELEGRAM_BOT_TOKENS (comma-separated): " TELEGRAM_BOT_TOKENS
read -p "Enter API_ID: " API_ID
read -p "Enter API_HASH: " API_HASH
read -p "Enter TELEGRAM_USER_ID: " TELEGRAM_USER_ID

# Create or update user_config.py with the provided values
cat <<EOL > user_config.py
USER_ID = "$USER_ID"
USER_AGENT = "$USER_AGENT"
X_BC = "$X_BC"
SESS_COOKIE = "$SESS_COOKIE"
TELEGRAM_BOT_TOKENS = [$TELEGRAM_BOT_TOKENS]
API_ID = '$API_ID'
API_HASH = '$API_HASH'
TELEGRAM_USER_ID = $TELEGRAM_USER_ID
EOL

echo "Configuration complete. Please run RUN.sh to start the bot."
