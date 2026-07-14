#include "DHT.h"

int pino_dht11 = 2;
DHT dht11(pino_dht11, DHT11);

void setup() {
  Serial.begin(9600);
  pinMode(13, OUTPUT);
  dht11.begin();
}

void loop() {
  delay(2000); // O DHT11 precisa de pelo menos ~2s entre leituras pra ser confiável

  float umidade = dht11.readHumidity();
  float temperatura = dht11.readTemperature();

  // Verifica se as leituras são válidas
  if (isnan(umidade) || isnan(temperatura)) {
    // Não manda nada pro Python quando a leitura falha, pra não gravar lixo no banco
    // (se quiser ver o erro no Monitor Serial, descomente a linha abaixo)
    // Serial.println("Falha na leitura");
  } else {

    Serial.print(umidade);
    Serial.print(";");
    Serial.println(temperatura);
  }

  if (temperatura >= 25) {
    digitalWrite(13, HIGH);
  } else {
    digitalWrite(13, LOW);
  }
}
