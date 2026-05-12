import tkinter as tk
from tkinter import messagebox

from geracordo.version_check import verificar_versao


def main() -> None:
    permitido, mensagem_bloqueio, aviso_nova_versao = verificar_versao()

    if not permitido:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Geracordo — Versao bloqueada", mensagem_bloqueio)
        root.destroy()
        return

    if aviso_nova_versao:
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo("Geracordo — Atualizacao disponivel", aviso_nova_versao)
        root.destroy()

    from geracordo.ui import launch_app
    launch_app()


if __name__ == "__main__":
    main()
