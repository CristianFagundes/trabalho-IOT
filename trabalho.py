import serial
import sqlite3
from datetime import datetime

try:
    porta = input("Digite a porta do Arduino, exemplo COM3: ")
    arduino = serial.Serial(porta, 9600)

    banco = sqlite3.connect("dados_da_tabela_do_cristian.db")
    cursor = banco.cursor()
    while True:
        linha = arduino.readline().decode().strip()
        if linha != "":
            dados = linha.split(";")
            if len(dados) == 2:
                valor_adc = float(dados[0])
                tensao = float(dados[1])
                data_hora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                cursor.execute("""
                INSERT INTO leituras (data_hora, valor_adc, tensao)VALUES (?, ?, ?)
                """, (data_hora, valor_adc, tensao))
                banco.commit()
                print(f"{data_hora} | ADC: {valor_adc} | Tensao: {tensao:.2f} V")
            else:
                print("Linha recebida em formato incorreto:", linha)

except KeyboardInterrupt:
    print("\nPrograma encerrado pelo usuario.")
finally:
    arduino.close()
    banco.close()
    print("Conexoes fechadas.")