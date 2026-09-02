#!/bin/bash
cd "$(dirname "$0")/.."
until [ -f build/esp32_fem_pico.ses ] || ! pgrep -x java >/dev/null; do sleep 10; done
sleep 3
./build/post_pico.sh > build/post_out.txt 2>&1
echo DONE >> build/post_out.txt
