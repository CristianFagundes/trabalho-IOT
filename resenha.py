"""
sistema_sensor.py
Versão 100% terminal (sem servidor web), pensada pra rodar sozinho na
máquina da faculdade, só com o sensor ligado por USB.

Funcionalidades (tudo pelo menu):
  1. Coletar dados do Arduino e gravar no banco
  2. Ver estatísticas de um período (min / máx / média)
  3. Ver gráfico histórico (abre uma janela com o gráfico, via matplotlib)
  4. Exportar relatório em CSV
  5. Sair

Dependências:
    pip install pyserial matplotlib
"""

import csv
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime

NOME_BANCO = "dados_da_tabela_do_cristian.db"
INTERVALO_RECONEXAO_SEGUNDOS = 5


# =========================================================
# BANCO DE DADOS
# =========================================================

@contextmanager
def conectar():
    banco = sqlite3.connect(NOME_BANCO)
    try:
        yield banco
    finally:
        banco.close()


def criar_tabela():
    with conectar() as banco:
        banco.execute("""
            CREATE TABLE IF NOT EXISTS leituras (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data_hora TEXT NOT NULL,
                valor_adc REAL NOT NULL,
                tensao REAL NOT NULL
            )
        """)
        banco.commit()


def inserir_leitura(data_hora, valor_adc, tensao):
    with conectar() as banco:
        banco.execute(
            "INSERT INTO leituras (data_hora, valor_adc, tensao) VALUES (?, ?, ?)",
            (data_hora, valor_adc, tensao),
        )
        banco.commit()


def _montar_where(inicio, fim):
    condicoes, parametros = [], []
    if inicio:
        condicoes.append("data_hora >= ?")
        parametros.append(inicio)
    if fim:
        condicoes.append("data_hora <= ?")
        parametros.append(fim)
    where = f"WHERE {' AND '.join(condicoes)}" if condicoes else ""
    return where, parametros


def buscar_leituras(inicio=None, fim=None, limite=1_000_000):
    with conectar() as banco:
        banco.row_factory = sqlite3.Row
        cursor = banco.cursor()
        where, parametros = _montar_where(inicio, fim)
        cursor.execute(f"""
            SELECT id, data_hora, valor_adc, tensao
            FROM leituras
            {where}
            ORDER BY data_hora ASC
            LIMIT ?
        """, (*parametros, limite))
        return [dict(linha) for linha in cursor.fetchall()]


def buscar_estatisticas(inicio=None, fim=None):
    with conectar() as banco:
        banco.row_factory = sqlite3.Row
        cursor = banco.cursor()
        where, parametros = _montar_where(inicio, fim)
        cursor.execute(f"""
            SELECT
                COUNT(*) AS total,
                MIN(tensao) AS tensao_min,
                MAX(tensao) AS tensao_max,
                AVG(tensao) AS tensao_media,
                MIN(valor_adc) AS adc_min,
                MAX(valor_adc) AS adc_max,
                AVG(valor_adc) AS adc_media
            FROM leituras
            {where}
        """, parametros)
        return dict(cursor.fetchone())


def buscar_media_por_hora(inicio=None, fim=None):
    with conectar() as banco:
        banco.row_factory = sqlite3.Row
        cursor = banco.cursor()
        where, parametros = _montar_where(inicio, fim)
        cursor.execute(f"""
            SELECT
                substr(data_hora, 1, 13) AS hora,
                AVG(tensao) AS tensao_media,
                AVG(valor_adc) AS adc_media,
                COUNT(*) AS total
            FROM leituras
            {where}
            GROUP BY hora
            ORDER BY hora ASC
        """, parametros)
        return [dict(linha) for linha in cursor.fetchall()]


# =========================================================
# COLETOR (Arduino -> Banco)
# =========================================================

def conectar_arduino(porta, baudrate=9600):
    import serial
    while True:
        try:
            arduino = serial.Serial(porta, baudrate, timeout=2)
            print(f"Conectado na porta {porta}.")
            return arduino
        except serial.SerialException as erro:
            print(f"Não foi possível conectar em {porta} ({erro}). "
                  f"Tentando de novo em {INTERVALO_RECONEXAO_SEGUNDOS}s...")
            time.sleep(INTERVALO_RECONEXAO_SEGUNDOS)


def opcao_coletar():
    import serial

    porta = input("Digite a porta do Arduino, exemplo COM3: ").strip()
    arduino = conectar_arduino(porta)

    print("Coletando dados. Pressione Ctrl+C para parar e voltar ao menu.\n")

    try:
        while True:
            try:
                linha_bruta = arduino.readline().decode(errors="ignore").strip()
            except serial.SerialException:
                print("Conexão com o Arduino caiu. Tentando reconectar...")
                arduino = conectar_arduino(porta)
                continue

            if not linha_bruta:
                continue

            dados = linha_bruta.split(";")
            if len(dados) != 2:
                print("Linha recebida em formato incorreto:", linha_bruta)
                continue

            try:
                valor_adc = float(dados[0])
                tensao = float(dados[1])
            except ValueError:
                print("Linha com valores não numéricos, ignorada:", linha_bruta)
                continue

            data_hora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            inserir_leitura(data_hora, valor_adc, tensao)
            print(f"{data_hora} | ADC: {valor_adc} | Tensao: {tensao:.2f} V")

    except KeyboardInterrupt:
        print("\nColeta pausada. Voltando ao menu.")
    finally:
        arduino.close()


# =========================================================
# RELATÓRIOS / GRÁFICOS (tudo no terminal)
# =========================================================

def pedir_periodo():
    """Pergunta um período opcional. Enter em branco = sem filtro."""
    print("\n(deixe em branco pra não filtrar por data)")
    inicio = input("Data/hora início (YYYY-MM-DD HH:MM:SS): ").strip() or None
    fim = input("Data/hora fim    (YYYY-MM-DD HH:MM:SS): ").strip() or None
    return inicio, fim


def opcao_estatisticas():
    inicio, fim = pedir_periodo()
    stats = buscar_estatisticas(inicio=inicio, fim=fim)

    print("\n===== ESTATÍSTICAS DO PERÍODO =====")
    if not stats["total"]:
        print("Nenhuma leitura encontrada nesse período.")
        return

    print(f"Total de registros : {stats['total']}")
    print(f"Tensão mínima       : {stats['tensao_min']:.2f} V")
    print(f"Tensão máxima       : {stats['tensao_max']:.2f} V")
    print(f"Tensão média        : {stats['tensao_media']:.2f} V")
    print(f"ADC mínimo          : {stats['adc_min']:.0f}")
    print(f"ADC máximo          : {stats['adc_max']:.0f}")
    print(f"ADC médio           : {stats['adc_media']:.1f}")
    print("====================================\n")


def opcao_grafico():
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("\nO matplotlib não está instalado. Rode: pip install matplotlib\n")
        return

    inicio, fim = pedir_periodo()

    print("Agrupamento: [1] leituras individuais  [2] média por hora")
    escolha = input("Escolha (1/2, padrão 2): ").strip() or "2"

    if escolha == "1":
        dados = buscar_leituras(inicio=inicio, fim=fim)
        eixo_x = [d["data_hora"] for d in dados]
        tensao = [d["tensao"] for d in dados]
        adc = [d["valor_adc"] for d in dados]
    else:
        dados = buscar_media_por_hora(inicio=inicio, fim=fim)
        eixo_x = [d["hora"] for d in dados]
        tensao = [d["tensao_media"] for d in dados]
        adc = [d["adc_media"] for d in dados]

    if not dados:
        print("Nenhuma leitura encontrada nesse período.\n")
        return

    # Se tiver muitos pontos, mostra só alguns rótulos no eixo X pra não poluir
    passo_rotulo = max(1, len(eixo_x) // 15)

    fig, eixo1 = plt.subplots(figsize=(10, 5))
    eixo1.plot(eixo_x, tensao, color="tab:blue", label="Tensão (V)")
    eixo1.set_xlabel("Data/hora")
    eixo1.set_ylabel("Tensão (V)", color="tab:blue")
    eixo1.tick_params(axis="y", labelcolor="tab:blue")
    eixo1.set_xticks(eixo_x[::passo_rotulo])
    eixo1.set_xticklabels(eixo_x[::passo_rotulo], rotation=45, ha="right", fontsize=8)

    eixo2 = eixo1.twinx()
    eixo2.plot(eixo_x, adc, color="tab:orange", label="Valor ADC")
    eixo2.set_ylabel("Valor ADC", color="tab:orange")
    eixo2.tick_params(axis="y", labelcolor="tab:orange")

    plt.title("Histórico de leituras do sensor")
    fig.tight_layout()
    print("\nAbrindo janela do gráfico... (feche a janela pra voltar ao menu)")
    plt.show()


def opcao_exportar_csv():
    inicio, fim = pedir_periodo()
    dados = buscar_leituras(inicio=inicio, fim=fim)

    if not dados:
        print("Nenhuma leitura encontrada nesse período. Nada foi exportado.\n")
        return

    nome_arquivo = input("Nome do arquivo CSV (padrão: relatorio_leituras.csv): ").strip()
    nome_arquivo = nome_arquivo or "relatorio_leituras.csv"
    if not nome_arquivo.endswith(".csv"):
        nome_arquivo += ".csv"

    with open(nome_arquivo, "w", newline="", encoding="utf-8") as arquivo:
        escritor = csv.writer(arquivo)
        escritor.writerow(["id", "data_hora", "valor_adc", "tensao"])
        for linha in dados:
            escritor.writerow([linha["id"], linha["data_hora"], linha["valor_adc"], linha["tensao"]])

    print(f"Relatório exportado para '{nome_arquivo}' ({len(dados)} registros).\n")


# =========================================================
# MENU PRINCIPAL
# =========================================================

def mostrar_menu():
    print("""
==================== SISTEMA DO SENSOR ====================
 1) Coletar dados do Arduino
 2) Ver estatisticas de um periodo (min/max/media)
 3) Ver grafico historico (janela matplotlib)
 4) Exportar relatorio em CSV
 5) Sair
=============================================================""")


def main():
    criar_tabela()
    while True:
        mostrar_menu()
        opcao = input("Escolha uma opcao: ").strip()

        if opcao == "1":
            opcao_coletar()
        elif opcao == "2":
            opcao_estatisticas()
        elif opcao == "3":
            opcao_grafico()
        elif opcao == "4":
            opcao_exportar_csv()
        elif opcao == "5":
            print("Encerrando. Ate mais!")
            break
        else:
            print("Opcao invalida, tente de novo.\n")


if __name__ == "__main__":
    main()