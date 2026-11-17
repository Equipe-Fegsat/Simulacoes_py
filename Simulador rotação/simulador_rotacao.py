"""
Simulador 3D da rotacao do Peabiru a partir do CSV gravado no cartao SD.

Mostra, sincronizados no tempo:
  - um cubo girando exatamente como o modelo estimou (roll, pitch, yaw), com os
    eixos do corpo (X vermelho, Y verde, Z azul), os eixos do mundo em cinza e
    um rastro da ponta do eixo Z;
  - o grafico da ALTURA (colorido por fase) e o da velocidade vertical, cada um
    com um ponto marcando o instante atual;
  - botao de play/pause e barra de tempo. O titulo mostra roll, pitch, yaw,
    altura, velocidade e altura maxima ate o momento.

Uso:
    python simulador_rotacao.py                    # abre janela para escolher o CSV
    python simulador_rotacao.py LOG000.CSV         # ou passa o caminho direto

Opcoes:
    --fps 20        quadros por segundo da animacao
    --vel 1         velocidade (1 = tempo real, 0.5 = camera lenta, 4 = 4x mais rapido)
    --dim 1 1 3     proporcoes do satelite em X Y Z (ex.: 1 1 3 para um CubeSat 3U)
    --relativo      mostra a rotacao relativa a primeira amostra (comeca alinhado)
    --sem-rastro    desliga o rastro da ponta do eixo Z

Convencao (a mesma do model.c):
    R (corpo -> mundo) = Rz(yaw) * Ry(pitch) * Rx(roll)
    Mundo: Z para cima. X/Y sao arbitrarios (sem magnetometro o yaw nao tem
    referencia absoluta e deriva com o tempo).
    A altura (alt_m) e a do filtro: metros acima do ponto onde o modelo calibrou.
"""
import argparse
import os

import numpy as np
import pandas as pd
import plotly.graph_objects as go

NOMES_FASE = {0: "PAD", 1: "BOOST", 2: "COAST", 3: "DESCENT", 4: "LANDED"}

COR_X, COR_Y, COR_Z = "#e74c3c", "#27ae60", "#2980b9"
CORES_FASE = {0: "gray", 1: "red", 2: "orange", 3: "blue", 4: "green"}
RASTRO_S = 2.0   # segundos de rastro


# --------------------------------------------------------------------------
# Leitura
# --------------------------------------------------------------------------
def ler_rotacao(arquivo):
    df = pd.read_csv(arquivo, on_bad_lines="skip")

    obrigatorias = ["t_ms", "roll_deg", "pitch_deg", "yaw_deg"]
    faltando = [c for c in obrigatorias if c not in df.columns]
    if faltando:
        raise ValueError(
            f"Colunas ausentes: {', '.join(faltando)}. O CSV e de uma versao antiga "
            f"do log (cabecalho com menos colunas)?"
        )

    for c in obrigatorias + [c for c in ("fase", "alt_m", "vel_ms") if c in df.columns]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df = df.dropna(subset=obrigatorias).sort_values("t_ms").reset_index(drop=True)
    if df.empty:
        raise ValueError("Nenhuma linha valida no CSV.")
    df["t_s"] = (df["t_ms"] - df["t_ms"].iloc[0]) / 1000.0
    return df


# --------------------------------------------------------------------------
# Geometria
# --------------------------------------------------------------------------
def matrizes_rotacao(roll_deg, pitch_deg, yaw_deg):
    """R (corpo -> mundo) para varias amostras. Retorna array (N, 3, 3)."""
    r, p, y = np.radians(roll_deg), np.radians(pitch_deg), np.radians(yaw_deg)
    cr, sr = np.cos(r), np.sin(r)
    cp, sp = np.cos(p), np.sin(p)
    cy, sy = np.cos(y), np.sin(y)

    R = np.empty((len(r), 3, 3))
    R[:, 0, 0] = cy * cp
    R[:, 0, 1] = cy * sp * sr - sy * cr
    R[:, 0, 2] = cy * sp * cr + sy * sr
    R[:, 1, 0] = sy * cp
    R[:, 1, 1] = sy * sp * sr + cy * cr
    R[:, 1, 2] = sy * sp * cr - cy * sr
    R[:, 2, 0] = -sp
    R[:, 2, 1] = cp * sr
    R[:, 2, 2] = cp * cr
    return R


def geometria_cubo(dim):
    dx, dy, dz = np.array(dim, dtype=float) / 2.0
    V = np.array([
        [-dx, -dy, -dz], [dx, -dy, -dz], [dx, dy, -dz], [-dx, dy, -dz],   # base (-Z)
        [-dx, -dy,  dz], [dx, -dy,  dz], [dx, dy,  dz], [-dx, dy,  dz],   # topo (+Z)
    ])
    # 12 triangulos (2 por face) e a cor de cada face
    tri = [
        ([0, 1, 2], [0, 2, 3], "#aed6f1"),   # -Z
        ([4, 5, 6], [4, 6, 7], COR_Z),       # +Z  (nariz)
        ([0, 1, 5], [0, 5, 4], "#a9dfbf"),   # -Y
        ([3, 2, 6], [3, 6, 7], COR_Y),       # +Y
        ([0, 3, 7], [0, 7, 4], "#f5b7b1"),   # -X
        ([1, 2, 6], [1, 6, 5], COR_X),       # +X
    ]
    I, J, K, cores = [], [], [], []
    for a, b, cor in tri:
        for t in (a, b):
            I.append(t[0]); J.append(t[1]); K.append(t[2]); cores.append(cor)
    arestas = [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4),
               (0, 4), (1, 5), (2, 6), (3, 7)]
    return V, (I, J, K), cores, arestas


def linhas_arestas(Vw, arestas):
    Vw = np.round(Vw, 4)
    x, y, z = [], [], []
    for a, b in arestas:
        x += [float(Vw[a, 0]), float(Vw[b, 0]), None]
        y += [float(Vw[a, 1]), float(Vw[b, 1]), None]
        z += [float(Vw[a, 2]), float(Vw[b, 2]), None]
    return x, y, z


# --------------------------------------------------------------------------
# Figura
# --------------------------------------------------------------------------
def montar_figura(df, fps=20, vel=1.0, dim=(1, 1, 1), relativo=False, rastro=True):
    R_all = matrizes_rotacao(df["roll_deg"].values, df["pitch_deg"].values, df["yaw_deg"].values)
    if relativo:
        R0inv = R_all[0].T
        R_all = np.einsum("ij,njk->nik", R0inv, R_all)

    # amostras escolhidas: uma por quadro, em tempo uniforme (amostra mais proxima)
    t = df["t_s"].values
    passo = vel / fps
    t_alvo = np.arange(0.0, t[-1] + 1e-9, passo)
    idx = np.searchsorted(t, t_alvo)
    idx = np.clip(idx, 1, len(t) - 1)
    idx = np.where(np.abs(t[idx - 1] - t_alvo) < np.abs(t[idx] - t_alvo), idx - 1, idx)
    n_quadros = len(idx)

    V, (I, J, K), cores, arestas = geometria_cubo(dim)
    L = 0.9 * max(dim)
    lim = 1.3 * max(dim)
    n_rastro = max(2, int(RASTRO_S / passo))
    tem_fase = "fase" in df.columns

    tem_alt = "alt_m" in df.columns and df["alt_m"].notna().any()
    tem_vel = tem_alt and "vel_ms" in df.columns and df["vel_ms"].notna().any()
    if tem_alt:
        alt = df["alt_m"].ffill().bfill().values
        alt_max_ate_agora = np.maximum.accumulate(alt)
    if tem_vel:
        velv = df["vel_ms"].ffill().bfill().values

    # pontas do eixo Z em cada quadro (para o rastro)
    pontas_z = np.array([R_all[i] @ np.array([0, 0, L]) for i in idx])

    def tracos(k, completo=True):
        """completo=True: tracos com estilo (figura inicial).
        completo=False: so as coordenadas (quadros da animacao) -> HTML bem menor."""
        i = idx[k]
        Rk = R_all[i]
        Vw = np.round(V @ Rk.T, 4)
        ex, ey, ez = linhas_arestas(Vw, arestas)
        eixos = np.round(Rk @ np.diag([L, L, L]), 4)   # colunas = eixos X, Y, Z do corpo

        if completo:
            saida = [
                go.Mesh3d(x=Vw[:, 0], y=Vw[:, 1], z=Vw[:, 2], i=I, j=J, k=K,
                          facecolor=cores, flatshading=True, opacity=1.0,
                          lighting=dict(ambient=0.7, diffuse=0.6), showlegend=False,
                          hoverinfo="skip"),
                go.Scatter3d(x=ex, y=ey, z=ez, mode="lines",
                             line=dict(color="black", width=3), showlegend=False,
                             hoverinfo="skip"),
            ]
        else:
            saida = [go.Mesh3d(x=Vw[:, 0], y=Vw[:, 1], z=Vw[:, 2]),
                     go.Scatter3d(x=ex, y=ey, z=ez)]

        for col, cor, rot in ((0, COR_X, "X"), (1, COR_Y, "Y"), (2, COR_Z, "Z")):
            xs, ys, zs = [0, eixos[0, col]], [0, eixos[1, col]], [0, eixos[2, col]]
            if completo:
                saida.append(go.Scatter3d(
                    x=xs, y=ys, z=zs, mode="lines+text", text=["", rot],
                    textposition="top center", line=dict(color=cor, width=7),
                    showlegend=False, hoverinfo="skip"))
            else:
                saida.append(go.Scatter3d(x=xs, y=ys, z=zs))
        if rastro:
            a = max(0, k - n_rastro)
            pz = np.round(pontas_z[a:k + 1], 3)
            if completo:
                saida.append(go.Scatter3d(x=pz[:, 0], y=pz[:, 1], z=pz[:, 2], mode="lines",
                                          line=dict(color="rgba(41,128,185,0.55)", width=3),
                                          showlegend=False, hoverinfo="skip"))
            else:
                saida.append(go.Scatter3d(x=pz[:, 0], y=pz[:, 1], z=pz[:, 2]))
        return saida

    def marcadores(k, completo=True):
        """Pontos que andam sobre os graficos de altura e de velocidade."""
        i = idx[k]
        m = []
        if tem_alt:
            if completo:
                m.append(go.Scatter(x=[t[i]], y=[alt[i]], mode="markers", xaxis="x", yaxis="y",
                                    marker=dict(size=12, color="black", line=dict(width=2, color="white")),
                                    showlegend=False, hoverinfo="skip"))
            else:
                m.append(go.Scatter(x=[t[i]], y=[alt[i]]))
        if tem_vel:
            if completo:
                m.append(go.Scatter(x=[t[i]], y=[velv[i]], mode="markers", xaxis="x2", yaxis="y2",
                                    marker=dict(size=12, color="black", line=dict(width=2, color="white")),
                                    showlegend=False, hoverinfo="skip"))
            else:
                m.append(go.Scatter(x=[t[i]], y=[velv[i]]))
        return m

    def titulo(k):
        i = idx[k]
        tilt = np.degrees(np.arccos(np.clip(R_all[i, 2, 2], -1, 1)))
        fase = ""
        if tem_fase and not np.isnan(df["fase"].iloc[i]):
            fase = f" · fase {NOMES_FASE.get(int(df['fase'].iloc[i]), '?')}"
        linha2 = (f"roll {df['roll_deg'].iloc[i]:+.1f}° · pitch {df['pitch_deg'].iloc[i]:+.1f}° · "
                  f"yaw {df['yaw_deg'].iloc[i]:+.1f}° · inclinação do eixo Z {tilt:.1f}°")
        if tem_alt:
            linha2 += f"<br>altura {alt[i]:.1f} m (máx. {alt_max_ate_agora[i]:.1f} m)"
            if tem_vel:
                linha2 += f" · velocidade vertical {velv[i]:+.1f} m/s"
        return f"Rotação do Peabiru — t = {t[i]:.2f} s{fase}<br><sup>{linha2}</sup>"

    base = tracos(0) + []
    n_cubo = len(base)

    # eixos do mundo (estaticos)
    mundo = []
    for vet, nome in (([lim, 0, 0], "X mundo"), ([0, lim, 0], "Y mundo"), ([0, 0, lim], "Z mundo (cima)")):
        mundo.append(go.Scatter3d(
            x=[0, vet[0]], y=[0, vet[1]], z=[0, vet[2]], mode="lines+text",
            text=["", nome], textposition="top center",
            line=dict(color="gray", width=2, dash="dot"), showlegend=False, hoverinfo="skip"))

    # curvas completas de altura (coloridas por fase) e de velocidade (estaticas)
    curvas = []
    if tem_alt:
        d = df.reset_index(drop=True)
        faseseg = d["fase"].fillna(-1) if tem_fase else pd.Series(0, index=d.index)
        seg_id = (faseseg != faseseg.shift()).cumsum()
        mostradas = set()
        for _, ix in d.groupby(seg_id).groups.items():
            ix = list(ix)
            a, b = ix[0], min(ix[-1] + 1, len(d) - 1)         # +1: sem buraco entre fases
            f = int(faseseg.iloc[a])
            nome = NOMES_FASE.get(f, "?")
            curvas.append(go.Scatter(
                x=t[a:b + 1], y=alt[a:b + 1], mode="lines", xaxis="x", yaxis="y",
                name=nome, legendgroup=nome, showlegend=nome not in mostradas,
                line=dict(color=CORES_FASE.get(f, "black"), width=3),
                hovertemplate="t = %{x:.2f} s<br>altura = %{y:.2f} m<extra>" + nome + "</extra>"))
            mostradas.add(nome)
    if tem_vel:
        curvas.append(go.Scatter(x=t, y=velv, mode="lines", xaxis="x2", yaxis="y2",
                                 line=dict(color="#2c3e50", width=2), showlegend=False,
                                 hovertemplate="t = %{x:.2f} s<br>vel = %{y:.2f} m/s<extra></extra>"))

    marc0 = marcadores(0)
    n_estaticos = len(mundo) + len(curvas)
    idx_marc = list(range(n_cubo + n_estaticos, n_cubo + n_estaticos + len(marc0)))
    traces_quadro = list(range(n_cubo)) + idx_marc

    quadros = [go.Frame(data=tracos(k, completo=False) + marcadores(k, completo=False),
                        traces=traces_quadro, name=str(k),
                        layout=go.Layout(title_text=titulo(k)))
               for k in range(n_quadros)]

    fig = go.Figure(data=base + mundo + curvas + marc0, frames=quadros)

    dur_ms = int(1000 / fps)
    com_graficos = tem_alt
    fig.update_layout(
        title=dict(text=titulo(0), x=0.02),
        scene=dict(
            domain=dict(x=[0.0, 0.58 if com_graficos else 1.0], y=[0.12, 1.0]),
            xaxis=dict(range=[-lim, lim], title="X", showbackground=False),
            yaxis=dict(range=[-lim, lim], title="Y", showbackground=False),
            zaxis=dict(range=[-lim, lim], title="Z (cima)", showbackground=False),
            aspectmode="cube",
            camera=dict(eye=dict(x=1.6, y=-1.6, z=0.9)),
        ),
        template="plotly_white",
        margin=dict(l=0, r=10, t=95, b=0),
        legend=dict(orientation="h", x=0.64, y=1.0, yanchor="bottom", title_text=""),
        updatemenus=[dict(
            type="buttons", direction="left", x=0.02, y=0.02, xanchor="left", yanchor="bottom",
            buttons=[
                dict(label="▶ Play", method="animate",
                     args=[None, dict(frame=dict(duration=dur_ms, redraw=True),
                                      transition=dict(duration=0),
                                      fromcurrent=True, mode="immediate")]),
                dict(label="⏸ Pause", method="animate",
                     args=[[None], dict(frame=dict(duration=0, redraw=False),
                                        transition=dict(duration=0), mode="immediate")]),
            ])],
        sliders=[dict(
            x=0.15, y=0.02, len=0.8, xanchor="left", yanchor="bottom",
            currentvalue=dict(prefix="t = ", visible=True),
            steps=[dict(method="animate", label=f"{t[idx[k]]:.1f}s",
                        args=[[str(k)], dict(mode="immediate",
                                             frame=dict(duration=0, redraw=True),
                                             transition=dict(duration=0))])
                   for k in range(n_quadros)])],
    )

    if com_graficos:
        t_fim = float(t[-1])
        lo, hi = float(np.min(alt)), float(np.max(alt))
        m = max(2.0, 0.08 * (hi - lo))
        fig.update_layout(
            xaxis=dict(domain=[0.66, 0.98], anchor="y", range=[0, t_fim], title="tempo (s)"),
            yaxis=dict(domain=[0.60, 0.92], anchor="x", range=[min(lo, 0) - m, max(hi, 5) + m],
                       title="Altura (m)", zeroline=True),
        )
        if tem_vel:
            vlo, vhi = float(np.min(velv)), float(np.max(velv))
            mv = max(1.0, 0.08 * (vhi - vlo))
            fig.update_layout(
                xaxis2=dict(domain=[0.66, 0.98], anchor="y2", range=[0, t_fim], title="tempo (s)"),
                yaxis2=dict(domain=[0.20, 0.48], anchor="x2", range=[min(vlo, -1) - mv, max(vhi, 1) + mv],
                            title="Vel. vertical (m/s)", zeroline=True),
            )
    return fig, n_quadros


# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Simulador 3D da rotacao do Peabiru")
    ap.add_argument("csv", nargs="?", help="arquivo CSV do cartao SD")
    ap.add_argument("--fps", type=float, default=20)
    ap.add_argument("--vel", type=float, default=1.0)
    ap.add_argument("--dim", type=float, nargs=3, default=(1, 1, 1), metavar=("X", "Y", "Z"))
    ap.add_argument("--relativo", action="store_true")
    ap.add_argument("--sem-rastro", action="store_true")
    args = ap.parse_args()

    arquivo = args.csv
    if not arquivo:
        from tkinter import Tk, filedialog
        root = Tk(); root.withdraw()
        arquivo = filedialog.askopenfilename(title="Selecione o CSV", filetypes=[("CSV", "*.csv")])
        if not arquivo:
            raise SystemExit("Nenhum arquivo selecionado.")

    df = ler_rotacao(arquivo)
    fig, n = montar_figura(df, fps=args.fps, vel=args.vel, dim=tuple(args.dim),
                           relativo=args.relativo, rastro=not args.sem_rastro)

    saida = os.path.splitext(arquivo)[0] + "_rotacao.html"
    fig.write_html(saida, auto_play=False)
    print(f"{n} quadros | {df['t_s'].iloc[-1]:.1f} s de log | salvo em: {saida}")
    fig.show()


if __name__ == "__main__":
    main()