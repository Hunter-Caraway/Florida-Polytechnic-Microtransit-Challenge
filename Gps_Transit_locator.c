/*
 * Minimal SIM7000A -> GNSS -> HTTPS POST -> Render/FastAPI
 *
 * What it does:
 *  - brings up PDP context with SpeedTalk APN "wholesale"
 *  - enables GNSS
 *  - waits for a live GPS fix
 *  - posts {"lat":..., "lon":..., "source":"sim7000_gnss"} to:
 *      https://florida-polytechnic-microtransit.onrender.com/devices/arduino_01/location
 *
 * IMPORTANT:
 *  - If your Render TRACKER_API_KEY is NOT "FortniteBattlePassTier27",
 *    change API_KEY below to the real value.
 *  - If your carrier/APN is not SpeedTalk wholesale, change APN below.
 */

#define F_CPU 16000000UL

#include <avr/io.h>
#include <util/delay.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <stdbool.h>
#include <stdint.h>

#define BAUD 9600
#define UBRR_VALUE ((F_CPU / 16 / BAUD) - 1)
#define RX_BUFFER_SIZE 512

#define APN        "wholesale"
#define HOST       "florida-polytechnic-microtransit.onrender.com"
#define URL_BASE   "https://florida-polytechnic-microtransit.onrender.com"
#define POST_URL   "https://florida-polytechnic-microtransit.onrender.com/devices/arduino_01/location"
#define API_KEY    "FortniteBattlePassTier27"

#define POST_OK         1
#define POST_FAIL       0
#define MODEM_FAIL     -1
#define GPS_FAIL       -2
#define NETWORK_FAIL   -3

// -----------------------------
// UART
// -----------------------------
static void UART_init(void) {
    UBRR0H = (uint8_t)(UBRR_VALUE >> 8);
    UBRR0L = (uint8_t)(UBRR_VALUE);

    UCSR0B = (1 << TXEN0) | (1 << RXEN0);
    UCSR0C = (1 << UCSZ01) | (1 << UCSZ00);
}

static void UART_sendChar(char c) {
    while (!(UCSR0A & (1 << UDRE0)));
    UDR0 = c;
}

static void UART_sendString(const char *s) {
    while (*s) UART_sendChar(*s++);
}

static bool UART_readCharTimeout(char *c, uint16_t timeout_ms) {
    while (timeout_ms--) {
        if (UCSR0A & (1 << RXC0)) {
            *c = UDR0;
            return true;
        }
        _delay_ms(1);
    }
    return false;
}

static void read_response(char *buf, size_t max_len, uint16_t timeout_ms) {
    size_t i = 0;
    char c;
    memset(buf, 0, max_len);

    while (i < max_len - 1) {
        if (!UART_readCharTimeout(&c, timeout_ms)) break;
        buf[i++] = c;
        buf[i] = '\0';
        timeout_ms = 50; // once data starts, keep reading in short bursts
    }
}

static void sendAT(const char *cmd) {
    UART_sendString(cmd);
    UART_sendString("\r\n");
}

static bool sendAT_expect(const char *cmd, const char *expect, uint16_t wait_ms) {
    char resp[RX_BUFFER_SIZE];
    sendAT(cmd);
    _delay_ms(200);
    read_response(resp, sizeof(resp), wait_ms);
    return strstr(resp, expect) != NULL;
}

// -----------------------------
// Modem setup
// -----------------------------
static bool modem_basic_check(void) {
    return sendAT_expect("AT", "OK", 1000);
}

static bool network_up(void) {
    // Quiet/basic config
    if (!sendAT_expect("ATE0", "OK", 1000)) return false;
    sendAT_expect("AT+CMEE=2", "OK", 1000);

    // SIM ready
    if (!sendAT_expect("AT+CPIN?", "READY", 3000)) return false;

    // PDP/APN config
    if (!sendAT_expect("AT+CGDCONT=1,\"IP\",\"" APN "\"", "OK", 3000)) return false;
    if (!sendAT_expect("AT+CNCFG=1,\"" APN "\"", "OK", 3000)) return false;

    // Activate data context
    // Some firmwares accept AT+CNACT=1,"apn", some use AT+CNACT=1 after CNCFG.
    // This version follows the documented CNCFG + CNACT flow first.
    if (!sendAT_expect("AT+CNACT=1", "OK", 10000)) {
        if (!sendAT_expect("AT+CNACT=1,\"" APN "\"", "OK", 10000)) {
            return false;
        }
    }

    // Verify IP assigned
    if (!sendAT_expect("AT+CNACT?", "+CNACT:", 5000)) return false;

    return true;
}

// -----------------------------
// GNSS
// -----------------------------
static bool gnss_enable(void) {
    if (!sendAT_expect("AT+CGNSPWR=1", "OK", 3000)) return false;
    sendAT_expect("AT+CGNSSEQ=\"RMC\"", "OK", 3000);
    return true;
}

static bool get_gps_fix(float *lat, float *lon) {
    char resp[RX_BUFFER_SIZE];
    char temp[RX_BUFFER_SIZE];
    char *payload;
    char *token;
    uint8_t field = 0;
    char fix_status[8] = {0};
    char lat_str[24] = {0};
    char lon_str[24] = {0};

    sendAT("AT+CGNSINF");
    _delay_ms(200);
    read_response(resp, sizeof(resp), 3000);

    payload = strstr(resp, "+CGNSINF:");
    if (!payload) return false;

    strncpy(temp, payload, sizeof(temp) - 1);
    temp[sizeof(temp) - 1] = '\0';

    payload = strchr(temp, ':');
    if (!payload) return false;
    payload++;

    token = strtok(payload, ",");
    while (token != NULL) {
        while (*token == ' ') token++;

        if (field == 1) {
            strncpy(fix_status, token, sizeof(fix_status) - 1);
        } else if (field == 3) {
            strncpy(lat_str, token, sizeof(lat_str) - 1);
        } else if (field == 4) {
            strncpy(lon_str, token, sizeof(lon_str) - 1);
            break;
        }

        token = strtok(NULL, ",");
        field++;
    }

    if (strcmp(fix_status, "1") != 0) return false;

    *lat = atof(lat_str);
    *lon = atof(lon_str);
    return true;
}

// -----------------------------
// HTTPS POST
// -----------------------------
static int post_location(float lat, float lon) {
    char resp[RX_BUFFER_SIZE];
    char cmd[320];
    char json[128];
    char lat_buf[24];
    char lon_buf[24];

    dtostrf(lat, 0, 6, lat_buf);
    dtostrf(lon, 0, 6, lon_buf);

    snprintf(
        json,
        sizeof(json),
        "{\"lat\":%s,\"lon\":%s,\"source\":\"sim7000_gnss\"}",
        lat_buf,
        lon_buf
    );

    // Clean up any stale session
    sendAT("AT+SHDISC");
    _delay_ms(300);
    read_response(resp, sizeof(resp), 2000);

    // TLS setup for hosted domain
    if (!sendAT_expect("AT+CSSLCFG=\"ignorertctime\",1,1", "OK", 3000)) return POST_FAIL;
    if (!sendAT_expect("AT+CSSLCFG=\"sslversion\",1,3", "OK", 3000)) return POST_FAIL;
    if (!sendAT_expect("AT+CSSLCFG=\"sni\",1,\"" HOST "\"", "OK", 3000)) return POST_FAIL;
    if (!sendAT_expect("AT+SHSSL=1,\"\"", "OK", 3000)) return POST_FAIL;

    // HTTP(S) client config
    if (!sendAT_expect("AT+SHCONF=\"URL\",\"" URL_BASE "\"", "OK", 3000)) return POST_FAIL;
    if (!sendAT_expect("AT+SHCONF=\"BODYLEN\",256", "OK", 3000)) return POST_FAIL;
    if (!sendAT_expect("AT+SHCONF=\"HEADERLEN\",350", "OK", 3000)) return POST_FAIL;
    sendAT_expect("AT+SHCONF=\"TIMEOUT\",60", "OK", 3000);

    if (!sendAT_expect("AT+SHCONN", "OK", 10000)) return POST_FAIL;

    if (!sendAT_expect("AT+SHCHEAD", "OK", 3000)) return POST_FAIL;
    if (!sendAT_expect("AT+SHAHEAD=\"Content-Type\",\"application/json\"", "OK", 3000)) return POST_FAIL;
    if (!sendAT_expect("AT+SHAHEAD=\"X_API_KEY\",\"" API_KEY "\"", "OK", 3000)) return POST_FAIL;

    snprintf(cmd, sizeof(cmd), "AT+SHBOD=\"%s\",%u", json, (unsigned)strlen(json));
    if (!sendAT_expect(cmd, "OK", 5000)) {
        sendAT_expect("AT+SHDISC", "OK", 3000);
        return POST_FAIL;
    }

    // Use the full URL here to match SIMCom examples as closely as possible
    sendAT("AT+SHREQ=\"" POST_URL "\",3");
    _delay_ms(200);
    read_response(resp, sizeof(resp), 15000);

    if (strstr(resp, ",200") || strstr(resp, ",201")) {
        sendAT("AT+SHREAD=0,128");
        _delay_ms(200);
        read_response(resp, sizeof(resp), 5000);
        sendAT_expect("AT+SHDISC", "OK", 3000);
        return POST_OK;
    }

    sendAT_expect("AT+SHDISC", "OK", 3000);
    return POST_FAIL;
}

// -----------------------------
// Main
// -----------------------------
int main(void) {
    float lat = 0.0f, lon = 0.0f;

    UART_init();
    _delay_ms(3000);

    if (!modem_basic_check()) {
        while (1) { _delay_ms(1000); }
    }

    if (!network_up()) {
        while (1) { _delay_ms(1000); }
    }

    if (!gnss_enable()) {
        while (1) { _delay_ms(1000); }
    }

    while (1) {
        bool have_fix = false;

        // Try up to ~60 seconds for a fix
        for (uint8_t i = 0; i < 30; i++) {
            if (get_gps_fix(&lat, &lon)) {
                have_fix = true;
                break;
            }
            _delay_ms(2000);
        }

        if (have_fix) {
            int result = post_location(lat, lon);

            if (result != POST_OK) {
                // Rebuild network on failure
                network_up();
            }
        }

        _delay_ms(15000);
    }
}