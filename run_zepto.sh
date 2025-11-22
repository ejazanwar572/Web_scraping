#!/bin/bash
# Activate virtual environment and run the Zepto price tracker
source venv/bin/activate

# Run with default settings (20% threshold, 560001 PIN)
python zepto_tracker.py "$@"