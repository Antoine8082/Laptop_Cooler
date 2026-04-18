"""
tray_app.py — Gestion du System Tray via pystray.
"""

import threading
import pystray
from pystray import MenuItem as item
from PIL import Image, ImageDraw, ImageFont
import os
import sys


def _get_icon_path():
    """Résout le chemin de l'icône (dev ou PyInstaller)."""
    if getattr(sys, 'frozen', False):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "assets", "icon.ico")


def _create_colored_icon(color="cyan"):
    """
    Crée une icône dynamique avec une turbine stylisée.
    Couleurs : 'green' (OK), 'orange' (chaud), 'red' (critique), 'cyan' (défaut).
    """
    size = 64
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    color_map = {
        "green": (76, 217, 100),
        "orange": (255, 159, 10),
        "red": (255, 59, 48),
        "cyan": (0, 199, 190),
        "gray": (128, 128, 128),
    }
    rgb = color_map.get(color, color_map["cyan"])

    # Cercle extérieur
    draw.ellipse([4, 4, 60, 60], outline=rgb, width=3)
    # Centre
    draw.ellipse([26, 26, 38, 38], fill=rgb)
    # Pales (4 lignes)
    center = 32
    for angle_offset in [(0, -20), (20, 0), (0, 20), (-20, 0)]:
        x2 = center + angle_offset[0]
        y2 = center + angle_offset[1]
        draw.line([(center, center), (x2, y2)], fill=rgb, width=3)

    return img


def _load_icon():
    """Charge l'icône depuis le fichier ou en crée une par défaut."""
    try:
        path = _get_icon_path()
        if os.path.exists(path):
            return Image.open(path)
    except Exception:
        pass
    return _create_colored_icon("cyan")


class TrayApp:
    """
    Application System Tray.
    
    Gère l'icône, le menu contextuel, et la communication avec la fenêtre tkinter.
    """

    def __init__(self, show_callback, pause_callback, quit_callback):
        """
        Args:
            show_callback: fonction appelée quand l'utilisateur clique "Ouvrir Réglages"
            pause_callback: fonction appelée pour toggle pause/resume
            quit_callback: fonction appelée quand l'utilisateur clique "Quitter"
        """
        self._show_cb = show_callback
        self._pause_cb = pause_callback
        self._quit_cb = quit_callback
        self._icon = None
        self._paused = False
        self._thread = None

    def start(self):
        """Démarre le system tray dans un thread séparé."""
        icon_image = _load_icon()

        menu = pystray.Menu(
            item("Ouvrir Réglages", self._on_show, default=True),
            item(
                lambda text: "▶ Reprendre" if self._paused else "⏸ Pause",
                self._on_pause,
            ),
            pystray.Menu.SEPARATOR,
            item("Quitter", self._on_quit),
        )

        self._icon = pystray.Icon(
            name="LaptopCooler",
            icon=icon_image,
            title="Laptop Cooler",
            menu=menu,
        )

        # pystray.Icon.run() est bloquant → thread dédié
        self._thread = threading.Thread(target=self._icon.run, daemon=True, name="TrayThread")
        self._thread.start()

    def stop(self):
        """Arrête le tray icon."""
        if self._icon is not None:
            try:
                self._icon.stop()
            except Exception:
                pass

    def update_icon_color(self, temp):
        """
        Met à jour la couleur de l'icône selon la température.
        
        Args:
            temp: température de référence (°C)
        """
        if self._icon is None:
            return

        if temp >= 85:
            color = "red"
        elif temp >= 70:
            color = "orange"
        elif temp > 0:
            color = "green"
        else:
            color = "gray"

        try:
            self._icon.icon = _create_colored_icon(color)
        except Exception:
            pass

    def update_tooltip(self, text):
        """Met à jour le tooltip du tray icon."""
        if self._icon is not None:
            try:
                self._icon.title = text
            except Exception:
                pass

    # ─── Callbacks du menu ───────────────────────────────────────────────────

    def _on_show(self, icon, menu_item):
        """Ouvre la fenêtre de réglages."""
        self._show_cb()

    def _on_pause(self, icon, menu_item):
        """Toggle pause/resume."""
        self._paused = not self._paused
        self._pause_cb(self._paused)
        # Forcer le rafraîchissement du menu
        self._icon.update_menu()

    def _on_quit(self, icon, menu_item):
        """Quitte l'application."""
        self._quit_cb()
