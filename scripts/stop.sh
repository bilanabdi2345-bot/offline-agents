#!/bin/bash
# Stops Second Brain. Nothing needs cleaning up, because nothing was saved.
pkill -f "secondbrain" && echo "Second Brain stopped." || echo "It wasn't running."
