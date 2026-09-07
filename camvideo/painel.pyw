#!/usr/bin/env python3
"""
painel - janelinha para trocar o que passa na camera do emulador.

Escolhe um video, prepara e instala como camera. Nao precisa de terminal:
de dois cliques neste arquivo (a extensao .pyw abre sem janela de console).

O emulador le sempre o mesmo arquivo:
    %LOCALAPPDATA%\\emulation-cam\\atual.mp4
Trocar esse arquivo troca o que a camera mostra. E o que este painel faz.
"""

import os
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, ttk

AQUI = os.path.dirname(os.path.abspath(__file__))
VIDEOS = os.path.join(AQUI, "videos")
MONTAR = os.path.join(AQUI, "montar.py")
AREA = os.path.expandvars(r"%LOCALAPPDATA%\emulation-cam")
ATUAL = os.path.join(AREA, "atual.mp4")
EXTS = (".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v")

LARGURA, ALTURA = 1280, 720


def achar(nome):
    achado = shutil.which(nome)
    if achado:
        return achado
    raiz = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages")
    if os.path.isdir(raiz):
        alvo = nome + ".exe"
        for pasta, _, arqs in os.walk(raiz):
            if alvo in arqs and os.path.basename(pasta) == "bin":
                return os.path.join(pasta, alvo)
    return None


def sem_console():
    """No Windows, nao pisca janela preta ao chamar o ffmpeg."""
    if os.name != "nt":
        return {}
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    return {"startupinfo": si, "creationflags": subprocess.CREATE_NO_WINDOW}


class Painel:
    def __init__(self, raiz):
        self.raiz = raiz
        self.escolhido = None
        self.ocupado = False
        raiz.title("Camera do emulador")
        raiz.geometry("560x520")
        raiz.minsize(480, 460)

        pad = {"padx": 12, "pady": 6}

        tk.Label(raiz, text="O que passa na camera",
                 font=("Segoe UI", 14, "bold")).pack(anchor="w", **pad)

        self.lbl_atual = tk.Label(raiz, text="", fg="#0a7", justify="left",
                                  anchor="w", font=("Segoe UI", 9))
        self.lbl_atual.pack(fill="x", **pad)

        tk.Label(raiz, text="Videos em camvideo/videos/",
                 font=("Segoe UI", 9)).pack(anchor="w", padx=12)

        quadro = tk.Frame(raiz)
        quadro.pack(fill="both", expand=True, padx=12, pady=4)
        barra = tk.Scrollbar(quadro)
        barra.pack(side="right", fill="y")
        self.lista = tk.Listbox(quadro, yscrollcommand=barra.set,
                                font=("Segoe UI", 10), activestyle="none")
        self.lista.pack(side="left", fill="both", expand=True)
        barra.config(command=self.lista.yview)
        self.lista.bind("<<ListboxSelect>>", self.ao_selecionar)
        self.lista.bind("<Double-Button-1>", lambda e: self.aplicar())

        linha = tk.Frame(raiz)
        linha.pack(fill="x", **pad)
        tk.Button(linha, text="Escolher outro arquivo...",
                  command=self.escolher_arquivo).pack(side="left")
        tk.Button(linha, text="Abrir a pasta",
                  command=lambda: os.startfile(VIDEOS)).pack(side="left", padx=6)
        tk.Button(linha, text="Atualizar lista",
                  command=self.carregar).pack(side="left")

        opc = tk.Frame(raiz)
        opc.pack(fill="x", **pad)
        self.cortar = tk.BooleanVar(value=False)
        tk.Checkbutton(opc, text="preencher a tela (corta as bordas)",
                       variable=self.cortar).pack(anchor="w")

        txt = tk.Frame(raiz)
        txt.pack(fill="x", **pad)
        tk.Label(txt, text="Texto por cima:").pack(side="left")
        self.texto = tk.Entry(txt)
        self.texto.pack(side="left", fill="x", expand=True, padx=6)

        self.btn = tk.Button(raiz, text="USAR ESTE VIDEO NA CAMERA",
                             font=("Segoe UI", 11, "bold"), height=2,
                             command=self.aplicar, state="disabled")
        self.btn.pack(fill="x", padx=12, pady=(10, 4))

        self.prog = ttk.Progressbar(raiz, mode="indeterminate")

        self.status = tk.Label(raiz, text="", anchor="w", justify="left",
                               fg="#555", font=("Segoe UI", 9), wraplength=520)
        self.status.pack(fill="x", padx=12, pady=(0, 10))

        self.carregar()
        self.mostrar_atual()

    # ---------------------------------------------------------------- dados
    def carregar(self):
        self.lista.delete(0, tk.END)
        self.arquivos = []
        if os.path.isdir(VIDEOS):
            for nome in sorted(os.listdir(VIDEOS)):
                if not nome.lower().endswith(EXTS):
                    continue
                # .pronto/.montado sao gerados por aqui; nao entram na lista
                base = os.path.splitext(nome)[0]
                if base.endswith((".pronto", ".montado")):
                    continue
                self.arquivos.append(os.path.join(VIDEOS, nome))
                self.lista.insert(tk.END, "  " + nome)
        if not self.arquivos:
            self.lista.insert(tk.END, "  (nenhum video aqui ainda)")
            self.dizer("Ponha videos em camvideo/videos/, ou use "
                       "'Escolher outro arquivo...'")

    def mostrar_atual(self):
        if os.path.isfile(ATUAL):
            mb = os.path.getsize(ATUAL) / (1024 * 1024)
            self.lbl_atual.config(
                text=f"Na camera agora: atual.mp4  ({mb:.1f} MB)\n{ATUAL}")
        else:
            self.lbl_atual.config(text="Na camera agora: (nada instalado ainda)",
                                  fg="#a60")

    def dizer(self, msg, cor="#555"):
        self.status.config(text=msg, fg=cor)
        self.raiz.update_idletasks()

    # --------------------------------------------------------------- acoes
    def ao_selecionar(self, _=None):
        sel = self.lista.curselection()
        if sel and self.arquivos and sel[0] < len(self.arquivos):
            self.escolhido = self.arquivos[sel[0]]
            self.btn.config(state="normal")
            self.dizer("Escolhido: " + os.path.basename(self.escolhido))

    def escolher_arquivo(self):
        caminho = filedialog.askopenfilename(
            title="Escolha um video",
            filetypes=[("Videos", "*.mp4 *.mov *.mkv *.webm *.avi *.m4v"),
                       ("Todos", "*.*")])
        if caminho:
            self.escolhido = caminho
            self.lista.selection_clear(0, tk.END)
            self.btn.config(state="normal")
            self.dizer("Escolhido: " + caminho)

    def aplicar(self):
        if self.ocupado or not self.escolhido:
            return
        self.ocupado = True
        self.btn.config(state="disabled", text="processando...")
        self.prog.pack(fill="x", padx=12, pady=(0, 6))
        self.prog.start(12)
        threading.Thread(target=self._trabalho, daemon=True).start()

    def _trabalho(self):
        try:
            os.makedirs(AREA, exist_ok=True)
            args = [sys.executable, MONTAR, "--fundo", self.escolhido,
                    "--ajuste", "cheio" if self.cortar.get() else "caber",
                    "--instalar", "-o", os.path.join(AREA, "trabalho.mp4")]
            t = self.texto.get().strip()
            if t:
                args += ["--texto", t]
            r = subprocess.run(args, capture_output=True, text=True,
                               **sem_console())
            if r.returncode != 0 or not os.path.isfile(ATUAL):
                erro = (r.stderr or r.stdout or "").strip().splitlines()
                self.raiz.after(0, self._fim, False,
                                erro[-1] if erro else "falhou sem mensagem")
            else:
                self.raiz.after(0, self._fim, True, None)
        except Exception as e:                                  # noqa: BLE001
            self.raiz.after(0, self._fim, False, str(e))

    def _fim(self, ok, erro):
        self.prog.stop()
        self.prog.pack_forget()
        self.ocupado = False
        self.btn.config(state="normal", text="USAR ESTE VIDEO NA CAMERA")
        self.mostrar_atual()
        if ok:
            self.dizer("Pronto. Suba o emulador pelo CAMERA.bat (opcao 1), ou "
                       "reinicie se ja estiver aberto -- ele le o arquivo no "
                       "boot.", "#0a7")
        else:
            self.dizer("Nao deu: " + erro, "#c00")


def main():
    if not achar("ffmpeg"):
        raiz = tk.Tk(); raiz.withdraw()
        from tkinter import messagebox
        messagebox.showerror("Falta o ffmpeg",
                             "Nao achei o ffmpeg.\n\n"
                             "Rode setup\\01-ferramentas.ps1, ou:\n"
                             "  winget install Gyan.FFmpeg")
        return
    raiz = tk.Tk()
    Painel(raiz)
    raiz.mainloop()


if __name__ == "__main__":
    main()
