"""
Simulador 3D AO VIVO do Peabiru: le a serial (UART4) e mostra, em tempo real,
a rotacao (cubo 3D), a ALTURA (grafico e numero grande), a velocidade vertical,
a altura maxima e a fase do voo.

O firmware precisa mandar uma linha curta (veja main_ao_vivo_trecho.c):
    R,<t_ms>,<roll>,<pitch>,<yaw>,<fase>,<altura_m>,<vel_ms>
Linhas antigas sem altura/velocidade (so ate <fase>) ainda funcionam: o cubo
gira e o painel de altura avisa que o firmware nao esta mandando esse dado.
Qualquer outra linha da serial e ignorada.

Uso:
    python simulador_ao_vivo.py                  # acha a porta sozinho
    python simulador_ao_vivo.py --porta /dev/tty.SLAB_USBtoUART
    python simulador_ao_vivo.py --simular        # sem placa: voo de teste

Opcoes: --baud 115200  --dim 1 1 3  --relativo  --sem-rastro  --janela 30
        (--janela = segundos de historico no grafico de altura)

IMPORTANTE: so um programa pode abrir a porta serial por vez. Feche o
"Serial Monitor" do VS Code antes de rodar este script.

Precisa estar na mesma pasta de simulador_rotacao.py (reaproveita a geometria
e a convencao dos angulos: R = Rz(yaw) * Ry(pitch) * Rx(roll), a mesma do model.c).
A altura e a do filtro (alt_m): metros acima do ponto onde o modelo calibrou.
"""
import argparse
import collections
import glob
import math
import sys
import threading
import time

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from mpl_toolkits.mplot3d.art3d import Poly3DCollection  # noqa: F401 (registra a projecao 3d)

from simulador_rotacao import (COR_X, COR_Y, COR_Z, NOMES_FASE, geometria_cubo,
                               matrizes_rotacao)


# --------------------------------------------------------------------------
# Protocolo
# --------------------------------------------------------------------------
def parse_linha(txt):
    """'R,t_ms,roll,pitch,yaw[,fase[,alt,vel]]' -> (t_ms, roll, pitch, yaw, fase, alt, vel) ou None.
    alt e vel vem como nan quando o firmware nao manda."""
    txt = txt.strip()
    if not txt.startswith("R,"):
        return None
    p = txt.split(",")
    if len(p) < 5:
        return None
    try:
        t = float(p[1])
        roll, pitch, yaw = float(p[2]), float(p[3]), float(p[4])
        fase = int(p[5]) if len(p) > 5 else -1
        alt = float(p[6]) if len(p) > 7 else math.nan
        vel = float(p[7]) if len(p) > 7 else math.nan
    except ValueError:
        return None
    # linha truncada/corrompida na serial: descarta
    if not (abs(roll) <= 360 and abs(pitch) <= 360 and abs(yaw) <= 360):
        return None
    if not (math.isnan(alt) or abs(alt) < 100000) or not (math.isnan(vel) or abs(vel) < 5000):
        return None
    return t, roll, pitch, yaw, fase, alt, vel


class Leitor(threading.Thread):
    """Le a serial numa thread; guarda a amostra mais recente e o historico de altura."""

    def __init__(self, fonte):
        super().__init__(daemon=True)
        self.fonte = fonte
        self.parar = False
        self.lock = threading.Lock()
        self.ultimo = None
        self.t_ultimo = 0.0
        self.recebidas = 0
        self.erro = None
        self.hist = collections.deque(maxlen=6000)   # (t_ms, alt, vel, fase)
        self.alt_max = math.nan

    def run(self):
        while not self.parar:
            try:
                linha = self.fonte.readline()
            except Exception as e:           # porta desconectada, etc.
                self.erro = str(e)
                return
            if not linha:
                continue
            if isinstance(linha, bytes):
                linha = linha.decode("ascii", errors="ignore")
            d = parse_linha(linha)
            if d:
                with self.lock:
                    if self.hist and d[0] < self.hist[-1][0]:    # placa reiniciou
                        self.hist.clear()
                        self.alt_max = math.nan
                    self.ultimo = d
                    self.t_ultimo = time.time()
                    self.recebidas += 1
                    if not math.isnan(d[5]):
                        self.hist.append((d[0], d[5], d[6], d[4]))
                        if math.isnan(self.alt_max) or d[5] > self.alt_max:
                            self.alt_max = d[5]


class FonteSimulada:
    """Imita a serial: gira o cubo, faz um 'voo' de 40 s e mistura linhas comuns."""

    def __init__(self, hz=25):
        self.dt = 1.0 / hz
        self.t0 = time.time()
        self.n = 0

    def readline(self):
        time.sleep(self.dt)
        t = time.time() - self.t0
        self.n += 1
        if self.n % 5 == 0:                  # linha "normal" da telemetria (deve ser ignorada)
            return b"[PAD] alt=0.04m vel=0.00m/s |a|=1.00g tilt=5.0deg\r\n"
        roll = 40 * math.sin(2 * math.pi * 0.20 * t)
        pitch = 30 * math.sin(2 * math.pi * 0.13 * t + 1.0)
        yaw = (30 * t) % 360 - 180
        u = (t % 40.0) / 40.0                # voo de 40 s que se repete
        alt = 120.0 * math.sin(math.pi * u) ** 2
        vel = 120.0 * 2 * math.sin(math.pi * u) * math.cos(math.pi * u) * math.pi / 40.0
        fase = 0 if u < 0.05 else 1 if u < 0.10 else 2 if u < 0.50 else 3 if u < 0.95 else 4
        return (f"R,{int(t * 1000)},{roll:.2f},{pitch:.2f},{yaw:.2f},{fase},"
                f"{alt:.2f},{vel:.2f}\r\n").encode()


def abrir_serial(porta, baud):
    try:
        import serial
        from serial.tools import list_ports
    except ImportError:
        raise SystemExit("Falta o pyserial. Instale com:  python -m pip install pyserial")

    if not porta:
        candidatos = []
        for padrao in ("/dev/cu.SLAB_USBtoUART*", "/dev/tty.SLAB_USBtoUART*",
                       "/dev/cu.usbserial*", "/dev/tty.usbserial*",
                       "/dev/cu.usbmodem*", "/dev/tty.usbmodem*"):
            candidatos += glob.glob(padrao)
        if not candidatos:
            disp = [p.device for p in list_ports.comports()]
            raise SystemExit("Nenhuma porta serial encontrada. Portas vistas: "
                             f"{disp or 'nenhuma'}. Passe a porta com --porta.")
        porta = candidatos[0]

    try:
        s = serial.Serial(porta, baud, timeout=0.2)
    except serial.SerialException as e:
        raise SystemExit(f"Nao consegui abrir {porta}: {e}\n"
                         "Feche o Serial Monitor do VS Code (ele segura a porta) e tente de novo.")
    print(f"Lendo {porta} a {baud} baud...")
    return s


# --------------------------------------------------------------------------
# Visualizacao
# --------------------------------------------------------------------------
def _set3d(linha, x, y, z):
    """Atualiza uma linha 3D (aceita listas; converte para arrays)."""
    x, y, z = (np.asarray(v, dtype=float) for v in (x, y, z))
    if hasattr(linha, "set_data_3d"):
        linha.set_data_3d(x, y, z)
    else:                                   # matplotlib mais antigo
        linha.set_data(x, y)
        linha.set_3d_properties(z)


COR_FASE = {0: "#7f8c8d", 1: "#e74c3c", 2: "#e67e22", 3: "#2980b9", 4: "#27ae60"}


class Visualizador:
    def __init__(self, leitor, dim=(1, 1, 1), relativo=False, rastro=True, n_rastro=60,
                 janela=30.0):
        self.leitor = leitor
        self.relativo = relativo
        self.R0inv = None
        self.rastro_on = rastro
        self.janela = janela
        self.pontas = collections.deque(maxlen=n_rastro)
        self._ult_cont, self._ult_t, self.taxa = 0, time.time(), 0.0

        V, (I, J, K), cores, arestas = geometria_cubo(dim)
        self.V, self.tri, self.arestas = V, list(zip(I, J, K)), arestas
        self.L = 0.9 * max(dim)
        lim = 1.3 * max(dim)

        # ---- layout: cubo 3D a esquerda; altura (grafico) e leitura numerica a direita
        self.fig = plt.figure(figsize=(13, 7))
        gs = self.fig.add_gridspec(2, 2, width_ratios=[1.25, 1], height_ratios=[1.6, 1],
                                   wspace=0.12, hspace=0.25)
        ax = self.ax = self.fig.add_subplot(gs[:, 0], projection="3d")
        ax.set_xlim(-lim, lim); ax.set_ylim(-lim, lim); ax.set_zlim(-lim, lim)
        ax.set_box_aspect((1, 1, 1))
        ax.set_xlabel("X"); ax.set_ylabel("Y")   # (sem rotulo no Z: ele invadia o grafico ao lado)
        ax.view_init(elev=20, azim=-50)

        self.poly = Poly3DCollection([V[list(t)] for t in self.tri], facecolors=cores,
                                     edgecolors="none", linewidths=0, alpha=1.0)
        ax.add_collection3d(self.poly)
        self.linha_arestas, = ax.plot([0], [0], [0], color="black", lw=1.5)

        nomes = ("X do corpo", "Y do corpo", "Z do corpo (nariz)")
        self.eixos = [ax.plot([0, 0], [0, 0], [0, 0], color=c, lw=4, label=n)[0]
                      for c, n in zip((COR_X, COR_Y, COR_Z), nomes)]
        for vet, nome in (((lim, 0, 0), "X mundo"), ((0, lim, 0), "Y mundo"),
                          ((0, 0, lim), "Z mundo (cima)")):
            ax.plot([0, vet[0]], [0, vet[1]], [0, vet[2]], color="gray", lw=1, ls=":")
            ax.text(*vet, nome, color="gray", fontsize=8)
        self.linha_rastro, = ax.plot([0], [0], [0], color=COR_Z, lw=1.5, alpha=0.5)
        ax.legend(loc="upper left", fontsize=8)

        # ---- grafico de altura
        self.ax_alt = self.fig.add_subplot(gs[0, 1])
        self.ax_alt.set_title("Altura (m)", fontsize=10)
        self.ax_alt.set_xlabel("segundos (0 = agora)")
        self.ax_alt.grid(alpha=0.3)
        self.ax_alt.axhline(0, color="gray", lw=0.8)
        self.linha_alt, = self.ax_alt.plot([], [], color="#2c3e50", lw=2)
        self.ponto_alt, = self.ax_alt.plot([], [], "o", color="#e74c3c", ms=7)
        self.ax_alt.set_xlim(-janela, 0)
        self.ax_alt.set_ylim(-2, 5)

        # ---- leitura numerica
        self.ax_txt = self.fig.add_subplot(gs[1, 1])
        self.ax_txt.axis("off")
        t = self.ax_txt.text
        self.txt_alt = t(0.02, 0.62, "-- m", fontsize=40, fontweight="bold", va="center")
        self.txt_alt_leg = t(0.02, 0.95, "ALTURA", fontsize=10, color="gray", va="top")
        self.txt_vel = t(0.02, 0.28, "", fontsize=16, va="center")
        self.txt_max = t(0.02, 0.10, "", fontsize=13, color="#555555", va="center")
        self.txt_fase = t(0.98, 0.62, "", fontsize=20, fontweight="bold", va="center", ha="right")

        self.titulo = self.fig.suptitle("Aguardando dados da serial...", fontsize=11)
        self._desenhar(np.eye(3))

    def _desenhar(self, R):
        Vw = self.V @ R.T
        self.poly.set_verts([Vw[list(t)] for t in self.tri])

        xs, ys, zs = [], [], []
        for a, b in self.arestas:
            xs += [Vw[a, 0], Vw[b, 0], np.nan]
            ys += [Vw[a, 1], Vw[b, 1], np.nan]
            zs += [Vw[a, 2], Vw[b, 2], np.nan]
        _set3d(self.linha_arestas, xs, ys, zs)

        eixos = R @ (self.L * np.eye(3))
        for col, lin in enumerate(self.eixos):
            _set3d(lin, [0, eixos[0, col]], [0, eixos[1, col]], [0, eixos[2, col]])

        if self.rastro_on:
            self.pontas.append(eixos[:, 2].copy())
            p = np.array(self.pontas)
            _set3d(self.linha_rastro, p[:, 0], p[:, 1], p[:, 2])

    def _atualizar_altura(self, d, hist, alt_max):
        _t, _r, _p, _y, fase, alt, vel = d
        if math.isnan(alt):
            self.txt_alt.set_text("--")
            self.txt_vel.set_text("firmware sem altura\n(atualize a linha R,... no main.c)")
            self.txt_max.set_text("")
            self.txt_fase.set_text("")
            return

        self.txt_alt.set_text(f"{alt:.1f} m")
        self.txt_vel.set_text(f"velocidade vertical  {vel:+.1f} m/s")
        self.txt_max.set_text(f"altura máxima  {alt_max:.1f} m")
        self.txt_fase.set_text(NOMES_FASE.get(fase, ""))
        self.txt_fase.set_color(COR_FASE.get(fase, "black"))

        if len(hist) >= 2:
            h = np.array(hist, dtype=float)                 # t_ms, alt, vel, fase
            x = (h[:, 0] - h[-1, 0]) / 1000.0
            m = x >= -self.janela
            x, y = x[m], h[m, 1]
            self.linha_alt.set_data(x, y)
            self.ponto_alt.set_data([x[-1]], [y[-1]])
            lo, hi = float(np.min(y)), float(np.max(y))
            margem = max(2.0, 0.1 * (hi - lo))
            self.ax_alt.set_ylim(min(lo, 0) - margem, max(hi, 5.0) + margem)

    def atualizar(self, _quadro=None):
        with self.leitor.lock:
            d, t_ult, cont = self.leitor.ultimo, self.leitor.t_ultimo, self.leitor.recebidas
            hist = list(self.leitor.hist)
            alt_max = self.leitor.alt_max

        agora = time.time()
        if agora - self._ult_t >= 1.0:           # taxa de recepcao (linhas/s)
            self.taxa = (cont - self._ult_cont) / (agora - self._ult_t)
            self._ult_cont, self._ult_t = cont, agora

        if self.leitor.erro:
            self.titulo.set_text(f"Serial desconectada: {self.leitor.erro}")
            return []
        if d is None:
            self.titulo.set_text("Aguardando dados da serial... (a placa precisa terminar a calibracao)")
            return []

        _t, roll, pitch, yaw, fase, _alt, _vel = d
        R = matrizes_rotacao(np.array([roll]), np.array([pitch]), np.array([yaw]))[0]
        if self.relativo:
            if self.R0inv is None:
                self.R0inv = R.T
            R = self.R0inv @ R
        self._desenhar(R)
        self._atualizar_altura(d, hist, alt_max)

        tilt = math.degrees(math.acos(max(-1.0, min(1.0, R[2, 2]))))
        atraso = agora - t_ult
        aviso = f"  ⚠ sem dados ha {atraso:.1f} s" if atraso > 1.0 else ""
        self.titulo.set_text(f"roll {roll:+.1f}° · pitch {pitch:+.1f}° · yaw {yaw:+.1f}° · "
                             f"inclinação Z {tilt:.1f}°   |   {self.taxa:.0f} linhas/s{aviso}")
        return []


# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Simulador 3D ao vivo da rotacao do Peabiru")
    ap.add_argument("--porta")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--simular", action="store_true", help="sem placa: usa uma fonte de teste")
    ap.add_argument("--dim", type=float, nargs=3, default=(1, 1, 1), metavar=("X", "Y", "Z"))
    ap.add_argument("--relativo", action="store_true")
    ap.add_argument("--sem-rastro", action="store_true")
    ap.add_argument("--janela", type=float, default=30.0, help="segundos de historico no grafico de altura")
    args = ap.parse_args()

    try:
        plt.switch_backend("TkAgg")      # o Tkinter ja esta funcionando no seu Python
    except Exception:
        pass

    fonte = FonteSimulada() if args.simular else abrir_serial(args.porta, args.baud)
    leitor = Leitor(fonte)
    leitor.start()

    viz = Visualizador(leitor, dim=tuple(args.dim), relativo=args.relativo,
                       rastro=not args.sem_rastro, janela=args.janela)
    anim = FuncAnimation(viz.fig, viz.atualizar, interval=33, blit=False,   # noqa: F841
                         cache_frame_data=False)
    try:
        plt.show()
    finally:
        leitor.parar = True
        if hasattr(fonte, "close"):
            fonte.close()


if __name__ == "__main__":
    main()