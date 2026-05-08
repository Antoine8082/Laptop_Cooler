"""
laptop_cooler.py — Point d'entrée principal de l'application Laptop Cooler.

Orchestre tous les composants :
  - Configuration persistante
  - Télémétrie matérielle (CPU/GPU)
  - Communication série Arduino
  - Contrôleur de régulation
  - Interface tkinter + System Tray
"""

import sys
import os
import tkinter as tk
import threading

# Ajouter le répertoire src au path
if getattr(sys, 'frozen', False):
    _base = sys._MEIPASS
else:
    _base = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, _base)

from config_manager import ConfigManager
from telemetry import HardwareMonitor
from serial_comm import SerialManager
from controller import CoolingController
from tray_app import TrayApp
from ui import SettingsWindow


class LaptopCoolerApp:
    """Application principale — orchestre tous les composants."""

    def __init__(self):
        # ── Composants ──
        self._config = ConfigManager()
        self._telemetry = HardwareMonitor()
        self._serial = SerialManager(
            port=self._config.get("serial_port", "COM3"),
            baudrate=self._config.get("baud_rate", 115200),
        )
        self._controller = CoolingController(self._config)

        # ── État ──
        self._paused = False
        self._running = True
        self._current_pwm = 0.0
        self._current_rpm = 0

        # ── Tkinter ──
        self._root = tk.Tk()
        self._root.withdraw()  # Caché au démarrage

        # ── UI ──
        self._ui = SettingsWindow(
            self._root, self._config, self._serial,
            on_apply_callback=self._on_settings_applied,
            on_turbine_toggle=self._on_turbine_toggle_ui,
        )

        # ── System Tray ──
        self._tray = TrayApp(
            show_callback=self._show_window,
            pause_callback=self._toggle_pause,
            quit_callback=self._quit,
        )

        # ── Gestion de la fermeture de la fenêtre ──
        self._root.protocol("WM_DELETE_WINDOW", self._hide_window)

    def run(self):
        """Lance l'application."""
        print("[App] Démarrage de Laptop Cooler...")

        # Démarrer le thread télémétrie (non-bloquant pour le thread principal)
        update_interval = self._config.get("update_interval_ms", 1000)
        self._telemetry.start(interval_ms=update_interval)

        # Démarrer le thread série
        self._serial.start()

        # Démarrer le tray
        self._tray.start()

        # Démarrer la boucle de mise à jour
        update_interval = self._config.get("update_interval_ms", 1000)
        self._root.after(update_interval, self._update_loop)

        # Boucle principale tkinter
        try:
            self._root.mainloop()
        except KeyboardInterrupt:
            self._quit()

    # ═════════════════════════════════════════════════════════════════════════
    #  BOUCLE DE MISE À JOUR
    # ═════════════════════════════════════════════════════════════════════════

    def _update_loop(self):
        """
        Boucle de mise à jour appelée périodiquement par root.after().
        Non-bloquante pour le thread principal tkinter.
        """
        if not self._running:
            return

        try:
            # 1. Lire la télémétrie (non-bloquant — le thread background fait l'update)
            telem = self._telemetry.get_data()

            # 2. Lire le RPM depuis la queue série
            rpm = self._serial.last_rpm
            self._current_rpm = rpm

            # 3. Calculer le PWM (sauf si en pause)
            if self._paused:
                pwm = 0.0
            else:
                pwm = max(6.0, self._controller.compute(telem))
                self._controller.notify_actual_pwm(pwm)  # Sync état interne avec valeur réelle
            self._current_pwm = pwm

            # 4. Envoyer la consigne à l'Arduino
            self._serial.send_pwm(int(pwm))

            # 5. Mettre à jour l'UI (si la fenêtre est visible)
            if self._root.winfo_viewable():
                self._ui.update_dashboard(telem, pwm, rpm)
                self._ui.update_status(
                    self._serial.status,
                    connected=self._serial.connected,
                )

            # 6. Mettre à jour l'icône tray
            temp_ref = max(telem.get("cpu_temp", 0), telem.get("gpu_temp", 0))
            self._tray.update_icon_color(temp_ref)
            self._tray.update_tooltip(
                f"Laptop Cooler — {temp_ref:.0f}°C | PWM {pwm:.0f}% | {rpm} RPM"
            )

        except Exception as e:
            print(f"[App] Erreur dans la boucle de mise à jour : {e}")

        # Replanifier
        if self._running:
            interval = self._config.get("update_interval_ms", 1000)
            self._root.after(interval, self._update_loop)

    # ═════════════════════════════════════════════════════════════════════════
    #  CALLBACKS
    # ═════════════════════════════════════════════════════════════════════════

    def _on_settings_applied(self, updates):
        """Callback quand l'utilisateur applique de nouveaux réglages."""
        print(f"[App] Réglages appliqués : {list(updates.keys())}")

        # Mettre à jour le port série si changé
        new_port = updates.get("serial_port")
        if new_port and new_port != self._serial._port:
            self._serial.set_port(new_port)
            print(f"[App] Port série changé → {new_port}")

        # Réinitialiser le contrôleur si la courbe change
        if "curve" in updates:
            self._controller.reset()

    def _show_window(self):
        """Affiche la fenêtre de réglages (appelé depuis le tray)."""
        # root.after est thread-safe pour tkinter
        self._root.after(0, self._ui.show)

    def _hide_window(self):
        """Cache la fenêtre dans le tray au lieu de quitter."""
        self._root.withdraw()

    def _on_turbine_toggle_ui(self, enabled):
        """Appelé par l'UI principale pour activer/désactiver le moteur."""
        self._toggle_pause(not enabled)

    def _toggle_pause(self, paused):
        """Toggle pause/resume de la régulation."""
        self._paused = paused
        # Synchroniser l'UI si l'action vient du tray
        if hasattr(self, '_ui') and self._ui:
            self._ui.set_turbine_state(not paused)
            
        if paused:
            self._serial.send_pwm(0)
            self._serial.pause()
            print("[App] Régulation en PAUSE — PWM → 0")
        else:
            self._serial.resume()
            self._controller.reset()
            print("[App] Régulation REPRISE")

    def _quit(self):
        """Arrêt propre de l'application."""
        print("[App] Arrêt en cours...")
        self._running = False

        # Couper le moteur
        try:
            self._serial.send_pwm(0)
            import time
            time.sleep(0.3)  # Laisser le temps à la commande de partir
        except Exception:
            pass

        # Arrêter les composants
        self._serial.stop()
        self._telemetry.close()
        self._tray.stop()

        # Quitter tkinter
        try:
            self._root.quit()
            self._root.destroy()
        except Exception:
            pass

        print("[App] Arrêt terminé.")
        os._exit(0)


# ═════════════════════════════════════════════════════════════════════════════
#  MAIN
# ═════════════════════════════════════════════════════════════════════════════

def main():
    """Point d'entrée."""
    app = LaptopCoolerApp()
    app.run()


if __name__ == "__main__":
    main()
