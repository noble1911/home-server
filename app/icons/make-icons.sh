#!/bin/bash
# Render Butler's icons (PWA + Android) from the SVGs in this folder.
# Needs rsvg-convert (brew install librsvg). Run from app/: ./icons/make-icons.sh
set -euo pipefail
cd "$(dirname "$0")/.."
render() { rsvg-convert -w "$2" -h "$2" "icons/$1" -o "$3"; }

render butler-icon.svg 192 public/icons/icon-192.png
render butler-icon.svg 512 public/icons/icon-512.png

RES=android/app/src/main/res
for pair in mdpi:48 hdpi:72 xhdpi:96 xxhdpi:144 xxxhdpi:192; do
  d=${pair%%:*}; s=${pair##*:}
  render butler-icon.svg "$s" "$RES/mipmap-$d/ic_launcher.png"
  render butler-round.svg "$s" "$RES/mipmap-$d/ic_launcher_round.png"
  render butler-foreground.svg $((s * 108 / 48)) "$RES/mipmap-$d/ic_launcher_foreground.png"
done
echo "icons rendered"
