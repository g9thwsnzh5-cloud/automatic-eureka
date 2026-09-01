#include "fem_rfx2401.h"

#include "driver/gpio.h"
#include "esp_log.h"
#include "esp_wifi.h"

static const char *TAG = "fem";

static esp_err_t fem_gpio_as_output(void)
{
    gpio_config_t io = {
        .pin_bit_mask = (1ULL << FEM_GPIO_TXEN) | (1ULL << FEM_GPIO_RXEN),
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_ENABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    return gpio_config(&io);
}

esp_err_t fem_rfx2401_init(void)
{
    esp_err_t err = fem_gpio_as_output();
    if (err != ESP_OK) {
        return err;
    }
    /* Safe default until the MAC takes over: receive mode. */
    gpio_set_level(FEM_GPIO_TXEN, 0);
    gpio_set_level(FEM_GPIO_RXEN, 1);
    return fem_rfx2401_auto();
}

esp_err_t fem_rfx2401_auto(void)
{
    /* Route the antenna-select bits to our two pins: bit0 -> TXEN, bit1 -> RXEN. */
    wifi_ant_gpio_config_t gpio_cfg = {0};
    gpio_cfg.gpio_cfg[0].gpio_select = 1;
    gpio_cfg.gpio_cfg[0].gpio_num = FEM_GPIO_TXEN;
    gpio_cfg.gpio_cfg[1].gpio_select = 1;
    gpio_cfg.gpio_cfg[1].gpio_num = FEM_GPIO_RXEN;
    esp_err_t err = esp_wifi_set_ant_gpio(&gpio_cfg);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "esp_wifi_set_ant_gpio: %s", esp_err_to_name(err));
        return err;
    }

    /* RX always uses "antenna 0" = code 0b10 (RXEN high),
       TX always uses "antenna 1" = code 0b01 (TXEN high). */
    wifi_ant_config_t ant = {
        .rx_ant_mode = WIFI_ANT_MODE_ANT0,
        .rx_ant_default = WIFI_ANT_ANT0,
        .tx_ant_mode = WIFI_ANT_MODE_ANT1,
        .enabled_ant0 = 2,
        .enabled_ant1 = 1,
    };
    err = esp_wifi_set_ant(&ant);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "esp_wifi_set_ant: %s", esp_err_to_name(err));
        return err;
    }
    ESP_LOGI(TAG, "FEM switching enabled: TXEN=GPIO%d RXEN=GPIO%d", FEM_GPIO_TXEN, FEM_GPIO_RXEN);
    return ESP_OK;
}

esp_err_t fem_rfx2401_force(bool txen, bool rxen)
{
    /* Take the pins back from the MAC and drive them as plain GPIO. */
    wifi_ant_gpio_config_t gpio_cfg = {0};
    esp_err_t err = esp_wifi_set_ant_gpio(&gpio_cfg);
    if (err != ESP_OK) {
        return err;
    }
    err = fem_gpio_as_output();
    if (err != ESP_OK) {
        return err;
    }
    gpio_set_level(FEM_GPIO_TXEN, txen);
    gpio_set_level(FEM_GPIO_RXEN, rxen);
    ESP_LOGW(TAG, "FEM forced: TXEN=%d RXEN=%d", txen, rxen);
    return ESP_OK;
}

esp_err_t fem_rfx2401_set_tx_power(int8_t power_qdbm)
{
    esp_err_t err = esp_wifi_set_max_tx_power(power_qdbm);
    if (err == ESP_OK) {
        int8_t got = 0;
        esp_wifi_get_max_tx_power(&got);
        ESP_LOGI(TAG, "ESP32 max TX power set to %.2f dBm", got / 4.0);
    }
    return err;
}
