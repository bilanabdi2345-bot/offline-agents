#!/bin/bash
# Stops Codicilix. Nothing needs cleaning up, because nothing was saved.
pkill -f "secondbrain" && echo "Codicilix stopped." || echo "It wasn't running."
