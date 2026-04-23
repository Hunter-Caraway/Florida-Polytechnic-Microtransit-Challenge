#include "BotleticsSIM7000.h"
#include <SoftwareSerial.h>
#include <string.h>

#define SIMCOM_7000
#define MODEM_RX 10
#define MODEM_TX 11

SoftwareSerial modemSS(MODEM_RX, MODEM_TX);
Botletics_modem_LTE modem = Botletics_modem_LTE();

const char HOST[]    = "florida-polytechnic-microtransit.onrender.com";
const int  PORT      = 443;
const char PATH[]    = "/devices/arduino_01/location";
const char API_KEY[] = "FortniteBattlePassTier27";
const char APN[]     = "Wholesale";

char lineBuf[192];
char request[170];

bool modemReady = false;
bool gpsReady = false;

void flushModem() {
  while (modemSS.available()) {
    modemSS.read();
  }
}

bool readLine(char *buf, size_t maxLen, unsigned long timeoutMs) {
  size_t idx = 0;
  unsigned long start = millis();

  while (millis() - start < timeoutMs) {
    while (modemSS.available()) {
      char c = modemSS.read();

      if (c == '\r') continue;

      if (c == '\n') {
        if (idx == 0) continue;
        buf[idx] = '\0';
        return true;
      }

      if (idx < maxLen - 1) {
        buf[idx++] = c;
      }
    }
  }

  buf[0] = '\0';
  return false;
}

bool readRawCGNSINF() {
  flushModem();

  Serial.println(F("---> AT+CGNSINF"));
  modemSS.println("AT+CGNSINF");

  unsigned long start = millis();

  while (millis() - start < 5000) {
    if (readLine(lineBuf, sizeof(lineBuf), 1000)) {
      Serial.print(F("<--- "));
      Serial.println(lineBuf);

      if (strncmp(lineBuf, "+CGNSINF:", 9) == 0) {
        char *p = lineBuf + 9;
        while (*p == ' ') p++;

        if (strncmp(p, "1,1,", 4) == 0) {
          Serial.println(F("RAWFIX"));
          Serial.println(lineBuf);
          return true;
        } else {
          return false;
        }
      }
    }
  }

  return false;
}

bool connectCellularOnce() {
  int n = modem.getNetworkStatus();
  if (!(n == 1 || n == 5)) {
    Serial.println(F("NO NET"));
    return false;
  }

  Serial.print(F("RSSI "));
  Serial.println(modem.getRSSI());

  modem.setNetworkSettings(F("Wholesale"));
  delay(1500);

  if (modem.enableGPRS(true)) {
    Serial.println(F("GPRS OK"));
    return true;
  }

  Serial.println(F("GPRS FAIL"));
  return false;
}

bool postRawFix() {
  // lineBuf is the full raw +CGNSINF line and is used directly as the payload
  snprintf(request, sizeof(request),
           "POST %s HTTP/1.1\r\n"
           "Host: %s\r\n"
           "X_API_KEY: %s\r\n"
           "Content-Type: text/plain\r\n"
           "Content-Length: %u\r\n"
           "Connection: close\r\n"
           "\r\n",
           PATH, HOST, API_KEY, strlen(lineBuf));

  Serial.println(F("POST"));
  Serial.println(lineBuf);

  if (modem.postData(HOST, PORT, "HTTPS", request, lineBuf)) {
    Serial.println(F("POST OK"));
    return true;
  }

  Serial.println(F("POST FAIL"));
  return false;
}

void setup() {
  Serial.begin(115200);
  delay(3000);
  Serial.println(F("BOOT"));

  modemSS.begin(9600);
  delay(1000);

  if (!modem.begin(modemSS)) {
    Serial.println(F("MODEM FAIL"));
    while (1);
  }

  modemReady = true;
  Serial.println(F("MODEM OK"));

  delay(10000);

  Serial.println(F("GPS CMD"));

  flushModem();
  Serial.println(F("---> AT+CGNSPWR=1"));
  modemSS.println("AT+CGNSPWR=1");

  bool ok = false;
  unsigned long start = millis();

  while (millis() - start < 5000) {
    if (readLine(lineBuf, sizeof(lineBuf), 1000)) {
      Serial.print(F("<--- "));
      Serial.println(lineBuf);

      if (strstr(lineBuf, "OK")) {
        ok = true;
        break;
      }

      if (strstr(lineBuf, "ERROR")) {
        break;
      }
    }
  }

  if (ok) {
    gpsReady = true;
    Serial.println(F("GPS ON"));
  } else {
    Serial.println(F("GPS FAIL"));
    while (1);
  }
}

void loop() {
  static unsigned long lastPostAttempt = 0;

  Serial.println(F("LOOP"));

  if (!modemReady || !gpsReady) {
    Serial.println(F("NOT READY"));
    delay(5000);
    return;
  }

  if (readRawCGNSINF()) {
    // Only try to post every 10 seconds
    if (millis() - lastPostAttempt >= 10000UL) {
      lastPostAttempt = millis();

      if (connectCellularOnce()) {
        postRawFix();
      } else {
        Serial.println(F("SKIP POST"));
      }
    }
  } else {
    Serial.println(F("NOFIX"));
  }

  delay(5000);
}
