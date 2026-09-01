# Firmware: FEM control + range test

ESP-IDF 5.x. Two parts:

- `components/fem_rfx2401` — reusable component. Enables MAC-driven TXEN/RXEN switching
  through the ESP32 antenna-select GPIO feature and limits the ESP32 output power so the
  RFX2401C input stays linear.
- `main` — range-test application: connects to an AP and prints RSSI every second.
  Optional 802.11 LR mode for ESP32-to-ESP32 links.

```bash
idf.py set-target esp32
idf.py menuconfig          # FEM board -> Wi-Fi SSID / password / TX power / LR mode
idf.py build flash monitor
```

## Using the component in another project (e.g. esp32_nat_router)

1. Copy `components/fem_rfx2401` into the project's `components/` directory.
2. After `esp_wifi_init()`: `fem_rfx2401_init();`
3. After `esp_wifi_start()`: `fem_rfx2401_set_tx_power(32);`  (32 = 8 dBm).

## Bring-up checks

- `fem_rfx2401_force(true, false)` puts the PA on continuously for power-meter tests.
  Never do this without an antenna or a 50 ohm load on J5.
- TP1 (TXEN) shows bursts during transmission, TP2 (RXEN) is high between them.
- If the antenna-index mapping turns out inverted on your IDF version (TX bursts on TP2),
  swap `enabled_ant0` / `enabled_ant1` in `fem_rfx2401.c`.
