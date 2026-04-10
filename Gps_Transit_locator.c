/*
 * GccApplication25.c
 *
 * Created: 4/3/2026 5:07:16 PM
 * Author : Jedih
 */ 

#include <avr/io.h>


#define F_CPU 16000000UL
#define BAUD 9600
#define UBRR_VALUE ((F_CPU/16/BAUD)-1)

void UART_init() {
	UBRR0H = (UBRR_VALUE >> 8);
	UBRR0L = UBRR_VALUE;

	UCSR0B = (1 << TXEN0) | (1 << RXEN0); // Enable TX/RX
	UCSR0C = (1 << UCSZ01) | (1 << UCSZ00); // 8-bit data
}

void UART_sendChar(char c) {
	while (!(UCSR0A & (1 << UDRE0)));
	UDR0 = c;
}

void UART_sendString(const char* str) {
	while (*str) {
		UART_sendChar(*str++);
	}
}

void sendAT(const char* cmd) {
	UART_sendString(cmd);
	UART_sendString("\r\n");
	_delay_ms(1000);
}

void sim7000_init() {
	sendAT("AT");              // Check communication
	sendAT("ATE0");            // Turn echo off
	sendAT("AT+CGATT=1");      // Attach to network
	sendAT("AT+SAPBR=3,1,\"CONTYPE\",\"GPRS\"");
	sendAT("AT+SAPBR=3,1,\"APN\",\"apn not yet have\""); // need to get a sim card 
	sendAT("AT+SAPBR=1,1");    // Open bearer
	sendAT("AT+SAPBR=2,1");    // Check IP
}

void send_location() {
	char json[200];

	float lat = 28.1234;
	float lon = -81.4567;

	sprintf(json,
	"{\"lat\":%.6f,\"lon\":%.6f,\"source\":\"sim7000\"}",
	lat, lon
	);

	sendAT("AT+HTTPINIT");
	sendAT("AT+HTTPPARA=\"CID\",1");

	sendAT("AT+HTTPPARA=\"URL\",\"http://server_To_send_to/devices/arduino_01/location\""); //wtv our server location is

	sendAT("AT+HTTPPARA=\"CONTENT\",\"application/json\"");

	// Send data length
	char data_cmd[50];
	sprintf(data_cmd, "AT+HTTPDATA=%d,10000", strlen(json));
	sendAT(data_cmd);

	_delay_ms(1000);
	UART_sendString(json);   // send JSON body
	_delay_ms(2000);
	sendAT("AT+HTTPPARA=\"USERDATA\",\"X_API_KEY: FortniteBattlePassTier27\"");
	sendAT("AT+HTTPACTION=1");  // POST
	_delay_ms(5000);

	sendAT("AT+HTTPTERM");
}
int main(void) {
	UART_init();
	_delay_ms(2000);

	sim7000_init();

	while (1) {
		send_location();
		_delay_ms(60000); // send every 60 sec
	}
}




