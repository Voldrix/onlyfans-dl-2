#!/bin/bash

# Update the package list
sudo apt-get update

# Install ffmpeg
sudo apt-get install -y ffmpeg

# Install python3 and python3-venv
sudo apt-get install -y python3 python3-pip python3-venv

# Create a virtual environment if it doesn't exist
if [ ! -d "myenv" ]; then
  python3 -m venv myenv
fi

# Activate the virtual environment
source myenv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install dependencies from requirements.txt
pip install -r requirements.txt

echo "Installation complete. Please run SETUP.sh to configure the bot."
