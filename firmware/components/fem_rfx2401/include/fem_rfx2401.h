#pragma once
/*
 * RFX2401C (or pin-compatible AT2401C) front-end control for ESP32.
 *
 * The FEM has two CMOS inputs:
 *   TXEN=1          -> PA on (transmit)
 *   TXEN=0, RXEN=1  -> LNA on (receive)
 *   TXEN=0, RXEN=0  -> chip shutdown (RF path is open!)
 *
 * The ESP32 Wi-Fi MAC can drive up to two GPIOs with the "antenna select"
 * code.  We use that hardware feature so the switching follows every TX/RX
 * turnaround with no CPU involvement: antenna index 1 (binary 01) is used for
 * TX and index 2 (binary 10) for RX.  With gpio[0] = TXEN and gpio[1] = RXEN
 * this produces exactly the truth table above.
 *
 * Board rev A: TXEN = GPIO23, RXEN = GPIO18.
 */
#include "esp_err.h"
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

#ifndef FEM_GPIO_TXEN
#define FEM_GPIO_TXEN 23
#endif
#ifndef FEM_GPIO_RXEN
#define FEM_GPIO_RXEN 18
#endif

/* Call after esp_wifi_init() and before esp_wifi_start(). */
esp_err_t fem_rfx2401_init(void);

/* Force a static state (for tests with a spectrum analyser / power meter). */
esp_err_t fem_rfx2401_force(bool txen, bool rxen);

/* Back to automatic MAC-driven switching. */
esp_err_t fem_rfx2401_auto(void);

/*
 * Limit the ESP32 output so the FEM input stays linear.  The RFX2401C input
 * P1dB is about +5 dBm; with the 0 ohm pad on the board keep the ESP32 at
 * <= +8 dBm (11n) so the PA output lands near +18..+20 dBm.
 * power_qdbm is in units of 0.25 dBm (ESP-IDF convention), e.g. 32 = 8 dBm.
 */
esp_err_t fem_rfx2401_set_tx_power(int8_t power_qdbm);

#ifdef __cplusplus
}
#endif
