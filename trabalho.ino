#include "DHT.h"

int pino_dht11 = 2;
DHT dht11(pino_dht11, DHT11);

void setup() {
  Serial.begin(9600);
  pinMode(13,OUTPUT);
  dht11.begin();
}

void loop() {
  delay(400); // Espera 2s por medição

  float umidade = dht11.readHumidity();
  float temperatura = dht11.readTemperature();

  // Verifica se as leituras são válidas
  if (isnan(umidade) || isnan(temperatura)) {
    Serial.println("Falha na leitura");
  } else {
    Serial.print("Umidade: ");
    Serial.print(umidade);
    Serial.print("%");
    Serial.print(" | ");
    Serial.print("Temperatura: ");
    Serial.print(temperatura);
    Serial.println("℃");
  }

  if(temperatura >= 25){
    digitalWrite(13,HIGH);
  }
  else{
    digitalWrite(13,LOW);
  }




}