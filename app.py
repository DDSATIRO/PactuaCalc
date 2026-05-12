import tkinter as tk
from tkinter import messagebox

from pactuacalc.version_check import verificar_versao


def main() -> None:
    permitido, mensagem_bloqueio, aviso_nova_versao = verificar_versao()

    if not permitido:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("PactuaCalc — Versao bloqueada", mensagem_bloqueio)
        root.destroy()
        return

    if aviso_nova_versao:
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo("PactuaCalc — Atualizacao disponivel", aviso_nova_versao)
        root.destroy()

    from pactuacalc.ui import launch_app
    launch_app()


if __name__ == "__main__":
    main()

