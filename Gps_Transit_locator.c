/*
 * gps_transit_locator.c
 * SIM7000A + GNSS + HTTPS POST (SpeedTalk Ready)
 */

#define F_CPU 16000000UL

#include <avr/io.h>
#include <util/delay.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <stdbool.h>

#define BAUD 9600
#define UBRR_VALUE ((F_CPU / 16 / BAUD) - 1)

#define RX_BUFFER_SIZE 512

// -----------------------------
// UART
// -----------------------------
void UART_init(void) {
    UBRR0H = (uint8_t)(UBRR_VALUE >> 8);
    UBRR0L = (uint8_t)(UBRR_VALUE);

    UCSR0B = (1 << TXEN0) | (1 << RXEN0);
    UCSR0C = (1 << UCSZ01) | (1 << UCSZ00);
}

void UART_sendChar(char c) {
    while (!(UCSR0A & (1 << UDRE0)));
    UDR0 = c;
}

void UART_sendString(const char *str) {
    while (*str) UART_sendChar(*str++);
}

bool UART_readCharTimeout(char *c, uint16_t timeout_ms) {
    while (timeout_ms--) {
        if (UCSR0A & (1 << RXC0)) {
            *c = UDR0;
            return true;
        }
        _delay_ms(1);
    }
    return false;
}

void read_response(char *buffer, size_t max_len, uint16_t timeout_ms) {
    size_t i = 0;
    char c;

    memset(buffer, 0, max_len);

    while (i < max_len - 1) {
        if (!UART_readCharTimeout(&c, timeout_ms)) break;
        buffer[i++] = c;
        buffer[i] = '\0';
        timeout_ms = 50;
    }
}

void sendAT(const char *cmd) {
    UART_sendString(cmd);
    UART_sendString("\r\n");
}

void sendAT_read(const char *cmd, char *resp, size_t max_len, uint16_t wait_ms) {
    sendAT(cmd);
    _delay_ms(200);
    read_response(resp, max_len, wait_ms);
}

// -----------------------------
// Helpers
// -----------------------------
bool response_contains(const char *resp, const char *needle) {
    return strstr(resp, needle) != NULL;
}

// -----------------------------
// SIM7000 Basic Check
// -----------------------------
bool sim7000_basic_check(void) {
    char resp[RX_BUFFER_SIZE];
    sendAT_read("AT", resp, sizeof(resp), 1000);
    return response_contains(resp, "OK");
}

// -----------------------------
// NETWORK INIT (FIXED)
// -----------------------------
void sim7000_init_network(void) {
    char resp[RX_BUFFER_SIZE];

    sendAT_read("ATE0", resp, sizeof(resp), 1000);
    sendAT_read("AT+CMEE=2", resp, sizeof(resp), 1000);

    // Force LTE Cat-M (important for SpeedTalk)
    sendAT_read("AT+CNMP=38", resp, sizeof(resp), 2000);
    sendAT_read("AT+CMNB=1", resp, sizeof(resp), 2000);

    // APN config (SpeedTalk)
    sendAT_read("AT+CGDCONT=1,\"IP\",\"wholesale\"", resp, sizeof(resp), 3000);
    sendAT_read("AT+SAPBR=3,1,\"CONTYPE\",\"GPRS\"", resp, sizeof(resp), 2000);
    sendAT_read("AT+SAPBR=3,1,\"APN\",\"wholesale\"", resp, sizeof(resp), 2000);

    // Attach to network
    sendAT_read("AT+CGATT=1", resp, sizeof(resp), 5000);

    // Check SIM + signal + registration
    sendAT_read("AT+CPIN?", resp, sizeof(resp), 2000);
    sendAT_read("AT+CSQ", resp, sizeof(resp), 2000);
    sendAT_read("AT+CREG?", resp, sizeof(resp), 3000);
    sendAT_read("AT+CEREG?", resp, sizeof(resp), 3000);

    // Open bearer
    sendAT_read("AT+SAPBR=1,1", resp, sizeof(resp), 10000);
    sendAT_read("AT+SAPBR=2,1", resp, sizeof(resp), 5000);
}

// -----------------------------
// GNSS
// -----------------------------
void sim7000_enable_gps(void) {
    char resp[RX_BUFFER_SIZE];
    sendAT_read("AT+CGNSPWR=1", resp, sizeof(resp), 2000);
    sendAT_read("AT+CGNSSEQ=\"RMC\"", resp, sizeof(resp), 2000);
}

bool get_gps_fix(float *lat, float *lon) {
    char resp[RX_BUFFER_SIZE];
    char temp[RX_BUFFER_SIZE];
    char *payload;
    char *token;
    uint8_t field = 0;
    char fix_status[8] = {0};
    char lat_str[24] = {0};
    char lon_str[24] = {0};

    sendAT_read("AT+CGNSINF", resp, sizeof(resp), 3000);

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

        if (field == 1) strncpy(fix_status, token, sizeof(fix_status) - 1);
        else if (field == 3) strncpy(lat_str, token, sizeof(lat_str) - 1);
        else if (field == 4) {
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
// HTTPS POST (IMPROVED CHECK)
// -----------------------------
bool https_post_location(float lat, float lon) {
    char resp[RX_BUFFER_SIZE];
    char json[128];
    char cmd[256];
    char lat_buf[24];
    char lon_buf[24];

    dtostrf(lat, 0, 6, lat_buf);
    dtostrf(lon, 0, 6, lon_buf);

    snprintf(json, sizeof(json),
             "{\"lat\":%s,\"lon\":%s,\"source\":\"sim7000\"}",
             lat_buf, lon_buf);

    sendAT_read("AT+CSSLCFG=\"sslversion\",1,3", resp, sizeof(resp), 3000);
    sendAT_read("AT+SHSSL=1,\"\"", resp, sizeof(resp), 3000);

    sendAT_read("AT+SHCONF=\"URL\",\"https://florida-polytechnic-microtransit.onrender.com\"", resp, sizeof(resp), 3000);
    sendAT_read("AT+SHCONF=\"BODYLEN\",256", resp, sizeof(resp), 3000);
    sendAT_read("AT+SHCONF=\"HEADERLEN\",256", resp, sizeof(resp), 3000);

    sendAT_read("AT+SHCONN", resp, sizeof(resp), 10000);

    sendAT_read("AT+SHCHEAD", resp, sizeof(resp), 3000);
    sendAT_read("AT+SHAHEAD=\"Content-Type\",\"application/json\"", resp, sizeof(resp), 3000);
    sendAT_read("AT+SHAHEAD=\"X_API_KEY\",\"FortniteBattlePassTier27\"", resp, sizeof(resp), 3000);

    snprintf(cmd, sizeof(cmd), "AT+SHBOD=\"%s\",%d", json, (int)strlen(json));
    sendAT_read(cmd, resp, sizeof(resp), 5000);

    sendAT_read("AT+SHREQ=\"/devices/arduino_01/location\",3", resp, sizeof(resp), 15000);

    // ✅ STRONG SUCCESS CHECK
    if (!(strstr(resp, ",200") || strstr(resp, ",201"))) {
        sendAT_read("AT+SHDISC", resp, sizeof(resp), 5000);
        return false;
    }

    sendAT_read("AT+SHREAD=0,256", resp, sizeof(resp), 5000);
    sendAT_read("AT+SHDISC", resp, sizeof(resp), 5000);

    return true;
}

// -----------------------------
// MAIN
// -----------------------------
int main(void) {
    float lat, lon;

    UART_init();
    _delay_ms(3000);

    if (!sim7000_basic_check()) {
        while (1);
    }

    sim7000_init_network();
    sim7000_enable_gps();

    while (1) {
        uint8_t attempts = 0;

        // Wait for GPS fix
        while (!get_gps_fix(&lat, &lon) && attempts < 10) {
            _delay_ms(2000);
            attempts++;
        }

        if (attempts < 10) {
            https_post_location(lat, lon);
        }

        _delay_ms(5000); // 5 seconds
    }
}
