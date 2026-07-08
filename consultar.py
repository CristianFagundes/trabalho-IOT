import sqlite3
banco = sqlite3.connect("dados_da_tabela_do_cristian.db")
cursor = banco.cursor()

cursor.execute("""
SELECT * FROM leituras
""")
resultados = cursor.fetchall()
for linha in resultados:
    print(linha)
banco.commit()
banco.close()