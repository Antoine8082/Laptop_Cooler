"""
telemetry.py — Lecture des capteurs CPU/GPU via LibreHardwareMonitorLib.dll (pythonnet).
"""

import os
import sys
import time
import threading

# ─── Résolution du chemin DLL ────────────────────────────────────────────────

def _get_dll_path():
    """Résout le chemin de LibreHardwareMonitorLib.dll (dev ou PyInstaller)."""
    if getattr(sys, 'frozen', False):
        # Mode PyInstaller : DLLs dans le sous-dossier DLL/ de _MEIPASS
        base = os.path.join(sys._MEIPASS, "DLL")
    else:
        # Mode développement : DLL dans le dossier DLL/ à la racine du projet
        base = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "DLL")

    dll = os.path.join(base, "LibreHardwareMonitorLib.dll")
    if not os.path.exists(dll):
        raise FileNotFoundError(f"LibreHardwareMonitorLib.dll introuvable : {dll}")
    return dll


# ─── Chargement pythonnet ────────────────────────────────────────────────────

def _get_dll_dir():
    """Retourne le répertoire contenant toutes les DLLs LHM."""
    if getattr(sys, 'frozen', False):
        return os.path.join(sys._MEIPASS, "DLL")
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "DLL")


try:
    import clr

    # Ajouter le répertoire DLL au path pour que .NET trouve les dépendances
    _dll_dir = _get_dll_dir()
    sys.path.insert(0, _dll_dir)

    # Configurer la résolution d'assemblies .NET pour les DLLs compagnons
    import System
    from System import AppDomain, ResolveEventHandler
    from System.Reflection import Assembly
    from System.IO import Path as DotNetPath

    def _resolve_assembly(sender, args):
        """Résout les assemblies .NET manquantes depuis le dossier DLL/."""
        name = args.Name.split(',')[0]  # Ex: "System.Memory" sans la version
        dll_file = os.path.join(_dll_dir, name + ".dll")
        if os.path.exists(dll_file):
            return Assembly.LoadFrom(dll_file)
        return None

    AppDomain.CurrentDomain.AssemblyResolve += ResolveEventHandler(_resolve_assembly)

    _dll_path = _get_dll_path()
    clr.AddReference(_dll_path)
    from LibreHardwareMonitor.Hardware import Computer, HardwareType, SensorType
    LHM_AVAILABLE = True
except Exception as e:
    print(f"[Telemetry] AVERTISSEMENT — LibreHardwareMonitor non disponible : {e}")
    LHM_AVAILABLE = False


# ─── Classe principale ──────────────────────────────────────────────────────

class HardwareMonitor:
    """
    Lit les températures et charges CPU/GPU via LibreHardwareMonitor.
    
    Nécessite les droits administrateur pour les capteurs de température.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._computer = None
        self._data = {
            "cpu_temp": 0.0,
            "gpu_temp": 0.0,
            "cpu_load": 0.0,
            "gpu_load": 0.0,
        }

        self._thread = None
        self._thread_running = False
        self._interval = 1.0  # secondes, mis à jour par start() ou set_interval()

        if LHM_AVAILABLE:
            try:
                self._computer = Computer()
                self._computer.IsCpuEnabled = True
                self._computer.IsGpuEnabled = True
                self._computer.Open()
                print("[Telemetry] LibreHardwareMonitor initialisé.")
            except Exception as e:
                print(f"[Telemetry] Erreur initialisation : {e}")
                self._computer = None

    def start(self, interval_ms=1000):
        """Démarre la lecture des capteurs dans un thread background."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._interval = interval_ms / 1000.0
        self._thread_running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="TelemetryThread")
        self._thread.start()

    def set_interval(self, interval_ms):
        """Met à jour l'intervalle de polling à chaud."""
        self._interval = max(0.1, interval_ms / 1000.0)

    def _run_loop(self):
        """Boucle interne du thread télémétrie."""
        while self._thread_running:
            try:
                self.update()
            except Exception as e:
                print(f"[Telemetry] Erreur thread : {e}")
            time.sleep(self._interval)

    def update(self):
        """
        Met à jour les données des capteurs.
        Retourne un dict avec cpu_temp, gpu_temp, cpu_load, gpu_load.
        """
        if not LHM_AVAILABLE or self._computer is None:
            return self._data.copy()

        cpu_temps = []
        gpu_temps = []
        cpu_load_total = None
        gpu_load_total = None

        try:
            for hardware in self._computer.Hardware:
                hardware.Update()

                # Parcourir aussi les sous-composants (ex: GPU sub-devices)
                for sub in hardware.SubHardware:
                    sub.Update()

                is_cpu = hardware.HardwareType in (
                    HardwareType.Cpu,
                )
                is_gpu = hardware.HardwareType in (
                    HardwareType.GpuNvidia,
                    HardwareType.GpuAmd,
                    HardwareType.GpuIntel,
                )

                for sensor in hardware.Sensors:
                    if sensor.Value is None:
                        continue

                    val = float(sensor.Value)

                    # --- Températures ---
                    if sensor.SensorType == SensorType.Temperature:
                        name_lower = sensor.Name.lower()
                        if "distance" in name_lower:
                            pass # Ignorer 'Distance to TjMax'
                        elif is_cpu:
                            cpu_temps.append((name_lower, val))
                        elif is_gpu:
                            gpu_temps.append((name_lower, val))

                    # --- Charges (Load) ---
                    elif sensor.SensorType == SensorType.Load:
                        name_lower = sensor.Name.lower()
                        if is_cpu and "total" in name_lower:
                            cpu_load_total = val
                        elif is_gpu and "core" in name_lower:
                            gpu_load_total = val

            def get_best_temp(temps_list, preferred_keywords):
                if not temps_list:
                    return 0.0
                for kw in preferred_keywords:
                    for name, val in temps_list:
                        if kw in name:
                            return val
                return max([v for n, v in temps_list])

            with self._lock:
                self._data["cpu_temp"] = get_best_temp(cpu_temps, ["package", "core max", "average", "core"])
                self._data["gpu_temp"] = get_best_temp(gpu_temps, ["gpu core", "core", "hot spot"])
                self._data["cpu_load"] = cpu_load_total if cpu_load_total is not None else 0.0
                self._data["gpu_load"] = gpu_load_total if gpu_load_total is not None else 0.0

        except Exception as e:
            print(f"[Telemetry] Erreur lecture capteurs : {e}")

        with self._lock:
            return self._data.copy()

    def get_data(self):
        """Retourne la dernière lecture sans mise à jour."""
        with self._lock:
            return self._data.copy()

    def close(self):
        """Arrête le thread et ferme proprement le Computer LHM."""
        self._thread_running = False
        if self._computer is not None:
            try:
                self._computer.Close()
                print("[Telemetry] LibreHardwareMonitor fermé.")
            except Exception:
                pass
            self._computer = None
