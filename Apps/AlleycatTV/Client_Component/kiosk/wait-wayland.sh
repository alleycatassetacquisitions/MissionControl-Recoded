#!/bin/sh
# Wait until labwc has created the Wayland socket.
uid="${1:?usage: wait-wayland.sh <uid>}"
sock="/run/user/${uid}/wayland-0"
i=0
while [ "$i" -lt 60 ]; do
  if [ -S "$sock" ]; then
    exit 0
  fi
  i=$((i + 1))
  sleep 1
done
echo "AlleycatTV: Wayland socket not ready at ${sock}" >&2
exit 1
