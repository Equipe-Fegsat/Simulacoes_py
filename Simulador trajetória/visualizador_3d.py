"""
Plot 3D da trajetoria do Peabiru a partir do CSV gravado no cartao SD.

Uso:
    python plot_trajetoria.py              # abre uma janela para escolher o CSV
    python plot_trajetoria.py LOG000.CSV   # ou passa o caminho direto

Observacao: X/Y vem de dead-reckoning (integracao da aceleracao) e DERIVA com
o tempo; a altitude vem do barometro (Kalman). Entao o grafico mostra bem a
subida/descida, mas o deslocamento horizontal e so uma estimativa.
"""
import os
import sys

import pandas as pd
import plotly.graph_objects as go

COLUNAS = ["x_m", "y_m", "alt_m", "fase"]

NOMES = {0: "PAD", 1: "BOOST", 2: "COAST", 3: "DESCENT", 4: "LANDED"}
CORES = {0: "gray", 1: "red", 2: "orange", 3: "blue", 4: "green"}


def escolher_arquivo():
    """Caminho passado na linha de comando ou janela de selecao."""
    if len(sys.argv) > 1:
        return sys.argv[1]

    from tkinter import Tk, filedialog

    root = Tk()
    root.withdraw()
    arquivo = filedialog.askopenfilename(
        title="Selecione o CSV", filetypes=[("CSV", "*.csv")]
    )
    if not arquivo:
        raise SystemExit("Nenhum arquivo selecionado.")
    return arquivo


def ler_dados(arquivo):
    # on_bad_lines="skip": ignora linhas corrompidas (ex.: energia cortada no meio)
    df = pd.read_csv(arquivo, on_bad_lines="skip")

    for coluna in COLUNAS:
        if coluna not in df.columns:
            raise ValueError(
                f"Coluna ausente: {coluna}. O CSV e de uma versao antiga do log "
                f"(cabecalho com menos colunas)?"
            )
        df[coluna] = pd.to_numeric(df[coluna], errors="coerce")

    if "t_ms" in df.columns:
        df["t_ms"] = pd.to_numeric(df["t_ms"], errors="coerce")

    # Linha truncada no fim do arquivo vira NaN e e descartada aqui
    df = df.dropna(subset=COLUNAS)

    if "t_ms" in df.columns:
        df = df.sort_values("t_ms")
        df["t_s"] = (df["t_ms"] - df["t_ms"].iloc[0]) / 1000.0

    return df.reset_index(drop=True)


def montar_figura(df):
    tem_tempo = "t_s" in df.columns
    fig = go.Figure()

    # Cada trecho CONTIGUO de uma fase vira uma linha. O trecho e estendido em
    # 1 ponto (o primeiro da fase seguinte) para nao ficar buraco entre fases.
    df = df.copy()
    df["segmento"] = (df["fase"] != df["fase"].shift()).cumsum()
    legendas_mostradas = set()

    for _, seg in df.groupby("segmento", sort=True):
        fase = int(seg["fase"].iloc[0])
        nome = NOMES.get(fase, f"Fase {fase}")

        primeiro, ultimo = seg.index[0], seg.index[-1]
        if ultimo + 1 < len(df):
            seg = df.loc[primeiro:ultimo + 1]

        hover = "X: %{x:.2f} m<br>Y: %{y:.2f} m<br>Altitude: %{z:.2f} m"
        if tem_tempo:
            hover += "<br>t: %{customdata:.2f} s"

        fig.add_trace(go.Scatter3d(
            x=seg["x_m"],
            y=seg["y_m"],
            z=seg["alt_m"],
            mode="lines",
            name=nome,
            legendgroup=nome,
            showlegend=nome not in legendas_mostradas,
            line=dict(color=CORES.get(fase, "black"), width=5),
            customdata=seg["t_s"] if tem_tempo else None,
            hovertemplate=hover + "<extra>" + nome + "</extra>",
        ))
        legendas_mostradas.add(nome)

    # Inicio
    inicio = df.iloc[0]
    fig.add_trace(go.Scatter3d(
        x=[inicio["x_m"]], y=[inicio["y_m"]], z=[inicio["alt_m"]],
        mode="markers", name="Início",
        marker=dict(size=6, color="black"),
    ))

    # Apogeu: procura so nas fases de voo (BOOST/COAST/DESCENT); se nao houve
    # voo, usa o maximo geral
    voo = df[df["fase"].isin([1, 2, 3])]
    base = voo if not voo.empty else df
    apogeu = base.loc[base["alt_m"].idxmax()]
    fig.add_trace(go.Scatter3d(
        x=[apogeu["x_m"]], y=[apogeu["y_m"]], z=[apogeu["alt_m"]],
        mode="markers+text", name="Apogeu",
        marker=dict(size=8, color="purple"),
        text=[f"Apogeu ({apogeu['alt_m']:.1f} m)"],
        textposition="top center",
    ))

    fig.update_layout(
        title=(
            "Trajetória 3D do Peabiru"
            "<br><sup>X/Y estimados por dead-reckoning (derivam com o tempo); "
            "altitude vem do barômetro</sup>"
        ),
        scene=dict(
            xaxis_title="X (m)",
            yaxis_title="Y (m)",
            zaxis_title="Altitude (m)",
            aspectmode="manual",
            aspectratio=dict(x=0.5, y=0.5, z=3.0),
        ),
        template="plotly_white",
        legend_title="Fases do voo",
    )
    return fig


def main():
    arquivo = escolher_arquivo()
    df = ler_dados(arquivo)

    if df.empty:
        raise SystemExit("Nenhuma linha valida no CSV.")

    fig = montar_figura(df)

    # Salva uma copia em HTML ao lado do CSV (da para abrir e compartilhar depois)
    saida = os.path.splitext(arquivo)[0] + "_trajetoria.html"
    fig.write_html(saida)
    print(f"Grafico salvo em: {saida}")

    fig.show()


if __name__ == "__main__":
    main()