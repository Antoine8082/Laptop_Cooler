"""
config_manager.py — Gestion de la configuration persistante (config.json).
"""

import json
import os
import sys
import threading
import copy

# ─── Valeurs par défaut ──────────────────────────────────────────────────────

DEFAULT_CONFIG = {
    "serial_port": "COM3",
    "baud_rate": 115200,
    "curve": {
        "40": 0,
        "50": 10,
        "60": 30,
        "70": 50,
        "80": 75,
        "90": 100
    },
    "hysteresis": 3,
    "alpha": 0.15,
    "max_rpm_limit": 28000,
    "overdrive": 0,
    "load_threshold": 70,
    "boost_pwm": 15,
    "fixed_speed_pwm": 10,
    "fixed_speed_mode": False,
    "update_interval_ms": 1000
}

MAX_RPM_ABSOLUTE = 28000  # RPM max physique du blower


def get_base_path():
    """Retourne le répertoire de base (compatible PyInstaller _MEIPASS)."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_config_path():
    """Retourne le chemin absolu vers config.json."""
    return os.path.join(get_base_path(), "config.json")


class ConfigManager:
    """Gestionnaire de configuration thread-safe avec persistance JSON."""

    def __init__(self):
        self._lock = threading.Lock()
        self._config = copy.deepcopy(DEFAULT_CONFIG)
        self._path = get_config_path()
        self.load()

    def load(self):
        """Charge la config depuis le fichier. Utilise les défauts si erreur."""
        with self._lock:
            try:
                if os.path.exists(self._path):
                    with open(self._path, 'r', encoding='utf-8') as f:
                        loaded = json.load(f)
                    # Fusion : les valeurs chargées écrasent les défauts
                    merged = copy.deepcopy(DEFAULT_CONFIG)
                    for key, value in loaded.items():
                        if key in merged:
                            if isinstance(merged[key], dict) and isinstance(value, dict):
                                merged[key].update(value)
                            else:
                                merged[key] = value
                    self._config = merged
                else:
                    self._config = copy.deepcopy(DEFAULT_CONFIG)
                    self._save_unlocked()
            except (json.JSONDecodeError, IOError, OSError):
                self._config = copy.deepcopy(DEFAULT_CONFIG)
                self._save_unlocked()

    def save(self):
        """Sauvegarde la config dans le fichier (thread-safe)."""
        with self._lock:
            self._save_unlocked()

    def _save_unlocked(self):
        """Écriture effective (doit être appelé sous le lock)."""
        try:
            with open(self._path, 'w', encoding='utf-8') as f:
                json.dump(self._config, f, indent=2, ensure_ascii=False)
        except (IOError, OSError) as e:
            print(f"[ConfigManager] Erreur sauvegarde: {e}")

    def get(self, key, default=None):
        """Récupère une valeur de config."""
        with self._lock:
            return copy.deepcopy(self._config.get(key, default))

    def set(self, key, value):
        """Modifie une valeur et sauvegarde."""
        with self._lock:
            self._config[key] = value
            self._save_unlocked()

    def get_all(self):
        """Retourne une copie complète de la config."""
        with self._lock:
            return copy.deepcopy(self._config)

    def update(self, partial_config):
        """Met à jour plusieurs clés à la fois et sauvegarde."""
        with self._lock:
            for key, value in partial_config.items():
                if key in self._config:
                    if isinstance(self._config[key], dict) and isinstance(value, dict):
                        self._config[key].update(value)
                    else:
                        self._config[key] = value
            self._save_unlocked()

    def get_curve(self):
        """Retourne la courbe triée sous forme de liste de tuples (temp, pwm)."""
        curve_dict = self.get("curve", {})
        return sorted([(int(k), v) for k, v in curve_dict.items()])
