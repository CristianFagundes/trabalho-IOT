"""
sistema_sensor.py
Tudo em um arquivo só: leitura do Arduino, banco de dados e servidor web
com relatórios/gráficos históricos.

Como usar:

  1) Rodar o servidor web (dashboard + API):
       python sistema_sensor.py servidor

  2) Rodar o coletor (lê o Arduino e grava no banco):
       python sistema_sensor.py coletor

Rode os dois ao mesmo tempo (em dois terminais). Se forem máquinas
diferentes, os dois precisam enxergar o mesmo arquivo .db (ex: pasta
compartilhada) ou rode tudo na mesma máquina (ex: um Raspberry Pi
ligado no Arduino, funcionando como servidor).

Dependências:
    pip install flask pyserial gunicorn
"""

import csv
import io
import sys
import time
import sqlite3
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


def buscar_leituras(inicio=None, fim=None, limite=1000):
    with conectar() as banco:
        banco.row_factory = sqlite3.Row
        cursor = banco.cursor()

        condicoes, parametros = [], []
        if inicio:
            condicoes.append("data_hora >= ?")
            parametros.append(inicio)
        if fim:
            condicoes.append("data_hora <= ?")
            parametros.append(fim)
        where = f"WHERE {' AND '.join(condicoes)}" if condicoes else ""

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

        condicoes, parametros = [], []
        if inicio:
            condicoes.append("data_hora >= ?")
            parametros.append(inicio)
        if fim:
            condicoes.append("data_hora <= ?")
            parametros.append(fim)
        where = f"WHERE {' AND '.join(condicoes)}" if condicoes else ""

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

        condicoes, parametros = [], []
        if inicio:
            condicoes.append("data_hora >= ?")
            parametros.append(inicio)
        if fim:
            condicoes.append("data_hora <= ?")
            parametros.append(fim)
        where = f"WHERE {' AND '.join(condicoes)}" if condicoes else ""

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


def rodar_coletor():
    import serial

    criar_tabela()
    porta = input("Digite a porta do Arduino, exemplo COM3: ").strip()
    arduino = conectar_arduino(porta)

    print("Coletando dados. Pressione Ctrl+C para parar.")

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
        print("\nPrograma encerrado pelo usuario.")
    finally:
        arduino.close()
        print("Conexao serial fechada.")


# =========================================================
# SERVIDOR WEB (Dashboard + API + Relatório)
# =========================================================

PAGINA_DASHBOARD = """
<!DOCTYPE html>
<html lang="pt-br">
<head>
<meta charset="UTF-8">
<title>Monitoramento do Sensor</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js"></script>
<style>
    body { font-family: Arial, sans-serif; background: #f4f6f8; margin: 0; padding: 24px; color: #222; }
    h1 { font-size: 22px; margin-bottom: 4px; }
    .subtitulo { color: #666; margin-bottom: 24px; }
    .cartoes { display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 24px; }
    .cartao { background: white; border-radius: 8px; padding: 16px 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); min-width: 150px; }
    .cartao .valor { font-size: 22px; font-weight: bold; }
    .cartao .rotulo { font-size: 12px; color: #777; text-transform: uppercase; }
    .filtros { background: white; padding: 16px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-bottom: 24px; display: flex; gap: 12px; align-items: end; flex-wrap: wrap; }
    .filtros label { display: block; font-size: 12px; color: #555; margin-bottom: 4px; }
    .filtros input, .filtros select, .filtros button { padding: 8px; border-radius: 4px; border: 1px solid #ccc; font-size: 14px; }
    .filtros button { background: #2563eb; color: white; border: none; cursor: pointer; }
    .filtros button:hover { background: #1d4ed8; }
    .filtros a.botao-csv { background: #16a34a; color: white; padding: 8px 12px; border-radius: 4px; text-decoration: none; font-size: 14px; }
    .grafico-container { background: white; padding: 16px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-bottom: 24px; }
    table { width: 100%; border-collapse: collapse; background: white; border-radius: 8px; overflow: hidden; }
    th, td { padding: 8px 12px; text-align: left; border-bottom: 1px solid #eee; font-size: 13px; }
    th { background: #f0f0f0; }
</style>
</head>
<body>

<h1>Monitoramento do Sensor</h1>
<div class="subtitulo">Histórico de leituras (ADC / Tensão)</div>

<div class="filtros">
    <div>
        <label>Data/hora início</label>
        <input type="datetime-local" id="inicio">
    </div>
    <div>
        <label>Data/hora fim</label>
        <input type="datetime-local" id="fim">
    </div>
    <div>
        <label>Agrupamento</label>
        <select id="agrupamento">
            <option value="bruto">Leituras individuais</option>
            <option value="hora" selected>Média por hora</option>
        </select>
    </div>
    <button onclick="atualizarTudo()">Aplicar filtro</button>
    <a class="botao-csv" id="link-csv" href="/relatorio/csv" target="_blank">Baixar CSV</a>
</div>

<div class="cartoes" id="cartoes">
    <div class="cartao"><div class="valor" id="c-total">--</div><div class="rotulo">Registros</div></div>
    <div class="cartao"><div class="valor" id="c-tensao-media">--</div><div class="rotulo">Tensão média (V)</div></div>
    <div class="cartao"><div class="valor" id="c-tensao-min">--</div><div class="rotulo">Tensão mínima (V)</div></div>
    <div class="cartao"><div class="valor" id="c-tensao-max">--</div><div class="rotulo">Tensão máxima (V)</div></div>
</div>

<div class="grafico-container">
    <canvas id="grafico" height="90"></canvas>
</div>

<div class="grafico-container">
    <h3 style="margin-top:0;">Últimas leituras</h3>
    <table id="tabela-leituras">
        <thead><tr><th>Data/hora</th><th>Valor ADC</th><th>Tensão (V)</th></tr></thead>
        <tbody></tbody>
    </table>
</div>

<script>
let grafico = null;

function paramsPeriodo() {
    const inicio = document.getElementById('inicio').value.replace('T', ' ');
    const fim = document.getElementById('fim').value.replace('T', ' ');
    const params = new URLSearchParams();
    if (inicio) params.append('inicio', inicio + ':00');
    if (fim) params.append('fim', fim + ':00');
    return params;
}

async function atualizarCartoes() {
    const params = paramsPeriodo();
    const resp = await fetch('/api/estatisticas?' + params.toString());
    const stats = await resp.json();
    document.getElementById('c-total').innerText = stats.total ?? 0;
    document.getElementById('c-tensao-media').innerText = stats.tensao_media ? stats.tensao_media.toFixed(2) : '--';
    document.getElementById('c-tensao-min').innerText = stats.tensao_min ? stats.tensao_min.toFixed(2) : '--';
    document.getElementById('c-tensao-max').innerText = stats.tensao_max ? stats.tensao_max.toFixed(2) : '--';
}

async function atualizarGrafico() {
    const agrupamento = document.getElementById('agrupamento').value;
    const params = paramsPeriodo();
    let labels = [], tensoes = [], adcs = [];

    if (agrupamento === 'hora') {
        const resp = await fetch('/api/media_por_hora?' + params.toString());
        const dados = await resp.json();
        labels = dados.map(d => d.hora);
        tensoes = dados.map(d => d.tensao_media);
        adcs = dados.map(d => d.adc_media);
    } else {
        params.append('limite', 2000);
        const resp = await fetch('/api/leituras?' + params.toString());
        const dados = await resp.json();
        labels = dados.map(d => d.data_hora);
        tensoes = dados.map(d => d.tensao);
        adcs = dados.map(d => d.valor_adc);
    }

    if (grafico) grafico.destroy();
    const ctx = document.getElementById('grafico').getContext('2d');
    grafico = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                { label: 'Tensão (V)', data: tensoes, borderColor: '#2563eb', backgroundColor: 'rgba(37,99,235,0.1)', tension: 0.2, pointRadius: 0 },
                { label: 'Valor ADC', data: adcs, borderColor: '#f59e0b', backgroundColor: 'rgba(245,158,11,0.1)', tension: 0.2, pointRadius: 0, yAxisID: 'y1' }
            ]
        },
        options: {
            responsive: true,
            interaction: { mode: 'index', intersect: false },
            scales: {
                y: { title: { display: true, text: 'Tensão (V)' } },
                y1: { position: 'right', title: { display: true, text: 'Valor ADC' }, grid: { drawOnChartArea: false } }
            }
        }
    });
}

async function atualizarTabela() {
    const params = paramsPeriodo();
    params.append('limite', 20);
    const resp = await fetch('/api/leituras?' + params.toString());
    let dados = await resp.json();
    dados = dados.slice(-20).reverse();

    const corpo = document.querySelector('#tabela-leituras tbody');
    corpo.innerHTML = '';
    for (const linha of dados) {
        const tr = document.createElement('tr');
        tr.innerHTML = `<td>${linha.data_hora}</td><td>${linha.valor_adc}</td><td>${linha.tensao.toFixed(2)}</td>`;
        corpo.appendChild(tr);
    }
}

function atualizarLinkCsv() {
    const params = paramsPeriodo();
    document.getElementById('link-csv').href = '/relatorio/csv?' + params.toString();
}

function atualizarTudo() {
    atualizarCartoes();
    atualizarGrafico();
    atualizarTabela();
    atualizarLinkCsv();
}

atualizarTudo();
setInterval(atualizarTudo, 30000);
</script>

</body>
</html>
"""


def rodar_servidor():
    from flask import Flask, jsonify, request, Response

    app = Flask(__name__)
    criar_tabela()

    @app.route("/")
    def dashboard():
        return PAGINA_DASHBOARD

    @app.route("/api/leituras")
    def api_leituras():
        inicio = request.args.get("inicio")
        fim = request.args.get("fim")
        limite = int(request.args.get("limite", 1000))
        return jsonify(buscar_leituras(inicio=inicio, fim=fim, limite=limite))

    @app.route("/api/media_por_hora")
    def api_media_por_hora():
        inicio = request.args.get("inicio")
        fim = request.args.get("fim")
        return jsonify(buscar_media_por_hora(inicio=inicio, fim=fim))

    @app.route("/api/estatisticas")
    def api_estatisticas():
        inicio = request.args.get("inicio")
        fim = request.args.get("fim")
        return jsonify(buscar_estatisticas(inicio=inicio, fim=fim))

    @app.route("/relatorio/csv")
    def relatorio_csv():
        inicio = request.args.get("inicio")
        fim = request.args.get("fim")
        dados = buscar_leituras(inicio=inicio, fim=fim, limite=1_000_000)

        buffer = io.StringIO()
        escritor = csv.writer(buffer)
        escritor.writerow(["id", "data_hora", "valor_adc", "tensao"])
        for linha in dados:
            escritor.writerow([linha["id"], linha["data_hora"], linha["valor_adc"], linha["tensao"]])

        return Response(
            buffer.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=relatorio_leituras.csv"},
        )

    app.run(host="0.0.0.0", port=8000, debug=True)


# =========================================================
# PONTO DE ENTRADA
# =========================================================

def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("servidor", "coletor"):
        print("Uso:")
        print("  python sistema_sensor.py servidor   -> sobe o dashboard/API")
        print("  python sistema_sensor.py coletor    -> lê o Arduino e grava no banco")
        sys.exit(1)

    if sys.argv[1] == "servidor":
        rodar_servidor()
    else:
        rodar_coletor()


if __name__ == "__main__":
    main()