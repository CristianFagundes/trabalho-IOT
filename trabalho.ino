#include "DHT.h"

int pino_dht11 = 2;

int pino_amarelo = 10;
int pino_vermelho = 13;
int pino_verde = 11;

DHT dht11(pino_dht11, DHT11);

void setup() {
  Serial.begin(9600);

  pinMode(pino_verde, OUTPUT);
  pinMode(pino_amarelo, OUTPUT);
  pinMode(pino_vermelho, OUTPUT);

  dht11.begin();
}

void loop() {
  // O DHT11 precisa de pelo menos 2 segundos entre leituras
  delay(2000);

  float umidade = dht11.readHumidity();
  float temperatura = dht11.readTemperature();

  // Verifica se a leitura foi válida
  if (isnan(umidade) || isnan(temperatura)) {
    // Se der erro, não faz nada nessa leitura
    return;
  }

  // Envia os dados para o Python
  Serial.print(umidade);
  Serial.print(";");
  Serial.println(temperatura);

  // Controle dos LEDs
  if (temperatura >= 28) {
    // Vermelho
    digitalWrite(pino_vermelho, HIGH);
    digitalWrite(pino_amarelo, LOW);
    digitalWrite(pino_verde, LOW);
  }
  else if (temperatura >= 26) {
    // Amarelo
    digitalWrite(pino_vermelho, LOW);
    digitalWrite(pino_amarelo, HIGH);
    digitalWrite(pino_verde, LOW);
  }
  else {
    // Verde
    digitalWrite(pino_vermelho, LOW);
    digitalWrite(pino_amarelo, LOW);
    digitalWrite(pino_verde, HIGH);
  }
}