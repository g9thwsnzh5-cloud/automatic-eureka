/*
 * Range-test firmware for the ESP32 Wi-Fi FEM board.
 *
 * - enables the RFX2401C switching (TXEN/RXEN follow the Wi-Fi MAC)
 * - limits the ESP32 output so the PA stays linear
 * - connects to an access point and prints RSSI once a second
 * - optional: 802.11 LR mode between two of these boards (menuconfig)
 *
 * Configure SSID/password with `idf.py menuconfig` -> "FEM board".
 */
#include <string.h>

#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "nvs_flash.h"

#include "fem_rfx2401.h"

static const char *TAG = "main";

static void on_wifi_event(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_START) {
        esp_wifi_connect();
    } else if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) {
        ESP_LOGW(TAG, "disconnected, retrying");
        vTaskDelay(pdMS_TO_TICKS(1000));
        esp_wifi_connect();
    } else if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t *ev = data;
        ESP_LOGI(TAG, "got ip " IPSTR, IP2STR(&ev->ip_info.ip));
    }
}

void app_main(void)
{
    ESP_ERROR_CHECK(nvs_flash_init());
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));

    /* FEM control must be configured after esp_wifi_init(). */
    ESP_ERROR_CHECK(fem_rfx2401_init());

    ESP_ERROR_CHECK(esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID, on_wifi_event, NULL));
    ESP_ERROR_CHECK(esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP, on_wifi_event, NULL));

    wifi_config_t sta = {0};
    strncpy((char *)sta.sta.ssid, CONFIG_FEM_WIFI_SSID, sizeof(sta.sta.ssid));
    strncpy((char *)sta.sta.password, CONFIG_FEM_WIFI_PASSWORD, sizeof(sta.sta.password));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &sta));

#if CONFIG_FEM_USE_LR_MODE
    /* Proprietary long-range PHY: only ESP32 <-> ESP32, ~1 km line of sight. */
    ESP_ERROR_CHECK(esp_wifi_set_protocol(WIFI_IF_STA, WIFI_PROTOCOL_LR));
#endif

    ESP_ERROR_CHECK(esp_wifi_start());

    /* Keep the FEM input linear: CONFIG_FEM_TX_POWER_QDBM defaults to 32 (= 8 dBm). */
    ESP_ERROR_CHECK(fem_rfx2401_set_tx_power(CONFIG_FEM_TX_POWER_QDBM));

    for (;;) {
        wifi_ap_record_t ap;
        if (esp_wifi_sta_get_ap_info(&ap) == ESP_OK) {
            ESP_LOGI(TAG, "RSSI %d dBm  ch %d  %s", ap.rssi, ap.primary, ap.ssid);
        }
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}
