#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <Adafruit_NeoPixel.h>

#define LED_PIN 5
#define LED_COUNT 64

const char* ssid = "Wokwi-GUEST";
const char* password = "";

// Replace with your server endpoint
const char* serverUrl = "http://your-server-ip/matrix";

Adafruit_NeoPixel matrix(
  LED_COUNT,
  LED_PIN,
  NEO_GRB + NEO_KHZ800
);

void connectWiFi() {
  WiFi.begin(ssid, password);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println("\nWiFi connected");
}

void fetchMatrixData() {
  if (WiFi.status() == WL_CONNECTED) {

    HTTPClient http;

    http.begin(serverUrl);

    int httpCode = http.GET();

    if (httpCode > 0) {

      String payload = http.getString();

      Serial.println(payload);

      DynamicJsonDocument doc(8192);

      DeserializationError error =
        deserializeJson(doc, payload);

      if (!error) {

        JsonArray pixels = doc["pixels"];

        for (int i = 0; i < LED_COUNT; i++) {

          int r = pixels[i][0];
          int g = pixels[i][1];
          int b = pixels[i][2];

          matrix.setPixelColor(
            i,
            matrix.Color(r, g, b)
          );
        }

        matrix.show();
      }
      else {
        Serial.println("JSON parse failed");
      }
    }
    else {
      Serial.println("HTTP request failed");
    }

    http.end();
  }
}

void setup() {

  Serial.begin(115200);

  matrix.begin();
  matrix.show();

  connectWiFi();
}

void loop() {

  fetchMatrixData();

  delay(100);
}