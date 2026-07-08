import sqlite3
banco = sqlite3.connect("dados_da_tabela_do_cristian.db")
cursor = banco.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS leituras (
id INTEGER PRIMARY KEY AUTOINCREMENT,
data_hora TEXT,
valor_adc INTEGER,
tensao REAL
)
""")
banco.commit()
banco.close()
print("Banco de dados criado com sucesso.")
print("Tabela 'leituras' criada com sucesso.")