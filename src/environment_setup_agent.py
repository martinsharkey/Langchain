import os
import sys

# Create a new virtual environment
os.system("python -m venv venv")

# Activate the virtual environment
os.system("source venv/bin/activate")

# Install required packages
os.system("pip install -r requirements.txt")