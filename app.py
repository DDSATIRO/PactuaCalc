import tkinter as tk
from tkinter import messagebox

from geracordo.version_check import verificar_versao


def main() -> None:
    permitido, mensagem = verificar_versao()
    if not permitido:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Geracordo — Versao bloqueada", mensagem)
        root.destroy()
        return

    from geracordo.ui import launch_app
    launch_app()


if __name__ == "__main__":
    main()
