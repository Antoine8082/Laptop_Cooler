"""
serial_comm.py — Communication série bidirectionnelle avec l'Arduino (thread dédié).
"""

import threading
import queue
import time
import serial
import serial.tools.list_ports


class SerialManager:
    """
    Gère la communication série avec l'Arduino en thread dédié.
    
    - Lecture asynchrone des lignes RPM (non-bloquante pour le thread principal).
    - Écriture des commandes PWM thread-safe.
    - Reconnexion automatique si le port est perdu.
    """

    def __init__(self, port="COM3", baudrate=115200):
        self._port = port
        self._baudrate = baudrate
        self._serial = None
        self._running = False
        self._connected = False
        self._paused = False

        # Queue thread-safe pour les RPM (le thread série écrit, le main lit)
        self.rpm_queue = queue.Queue(maxsize=10)

        # Queue pour les commandes PWM (le main écrit, le thread série lit)
        self._pwm_queue = queue.Queue(maxsize=10)

        # Dernière valeur RPM connue
        self._last_rpm = 0
        self._rpm_lock = threading.Lock()

        # Thread
        self._thread = None

        # Statut pour l'UI
        self._status = "Déconnecté"
        self._status_lock = threading.Lock()

    @property
    def connected(self):
        return self._connected

    @property
    def status(self):
        with self._status_lock:
            return self._status

    @status.setter
    def status(self, value):
        with self._status_lock:
            self._status = value

    @property
    def last_rpm(self):
        with self._rpm_lock:
            return self._last_rpm

    def set_port(self, port):
        """Change le port série (déconnecte et reconnecte)."""
        self._port = port
        self._disconnect()

    def start(self):
        """Démarre le thread de communication."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="SerialThread")
        self._thread.start()

    def stop(self):
        """Arrête le thread et ferme le port."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=3)
        self._disconnect()

    def send_pwm(self, value):
        """
        Envoie une consigne PWM à l'Arduino (0-100).
        Non-bloquant : place la commande dans une queue.
        """
        value = max(0, min(100, int(value)))
        # Vider les anciennes commandes pour ne garder que la plus récente
        while not self._pwm_queue.empty():
            try:
                self._pwm_queue.get_nowait()
            except queue.Empty:
                break
        try:
            self._pwm_queue.put_nowait(value)
        except queue.Full:
            pass

    def pause(self):
        """Met la communication en pause (envoie PWM:0)."""
        self._paused = True
        self.send_pwm(0)

    def resume(self):
        """Reprend la communication."""
        self._paused = False

    @staticmethod
    def list_ports():
        """Liste les ports COM disponibles."""
        ports = serial.tools.list_ports.comports()
        return [p.device for p in sorted(ports)]

    # ─── Boucle interne du thread ────────────────────────────────────────────

    def _run_loop(self):
        """Boucle principale du thread série."""
        while self._running:
            # Tentative de connexion si pas connecté
            if not self._connected:
                self._connect()
                if not self._connected:
                    time.sleep(3)  # Attendre avant de réessayer
                    continue

            try:
                # --- Écriture : envoyer les commandes PWM en attente ---
                self._process_pwm_queue()

                # --- Lecture : lire les lignes disponibles ---
                self._read_lines()

            except (serial.SerialException, OSError) as e:
                print(f"[Serial] Erreur communication : {e}")
                self._disconnect()
                self.status = "Déconnecté — reconnexion..."
                time.sleep(2)

    def _connect(self):
        """Tente d'ouvrir le port série."""
        try:
            self._serial = serial.Serial(
                port=self._port,
                baudrate=self._baudrate,
                timeout=1,          # Timeout lecture 1s (non-bloquant)
                write_timeout=1,
            )
            # Attendre que l'Arduino redémarre (reset DTR)
            time.sleep(2)
            # Vider le buffer
            self._serial.reset_input_buffer()
            self._connected = True
            self.status = "Connecté"
            print(f"[Serial] Connecté sur {self._port}")
        except (serial.SerialException, OSError) as e:
            self._connected = False
            self.status = f"Erreur : {e}"
            self._serial = None

    def _disconnect(self):
        """Ferme le port série proprement."""
        self._connected = False
        if self._serial is not None:
            try:
                self._serial.close()
            except Exception:
                pass
            self._serial = None
        self.status = "Déconnecté"

    def _process_pwm_queue(self):
        """Envoie les commandes PWM en attente."""
        try:
            while not self._pwm_queue.empty():
                value = self._pwm_queue.get_nowait()
                cmd = f"PWM:{value}\n"
                if self._serial and self._serial.is_open:
                    self._serial.write(cmd.encode('ascii'))
                    self._serial.flush()
        except queue.Empty:
            pass
        except (serial.SerialException, OSError):
            raise

    def _read_lines(self):
        """Lit les lignes disponibles sur le port série."""
        if self._serial is None or not self._serial.is_open:
            return

        # Lire tant qu'il y a des données (avec timeout de 1s max)
        while self._serial.in_waiting > 0 or True:
            try:
                line = self._serial.readline().decode('ascii', errors='ignore').strip()
            except serial.SerialTimeoutException:
                break
            except (serial.SerialException, OSError):
                raise

            if not line:
                break  # Timeout atteint, rien à lire

            # Parser la ligne
            if line.startswith("RPM:"):
                try:
                    rpm = int(line[4:])
                    with self._rpm_lock:
                        self._last_rpm = rpm
                    # Placer dans la queue (écraser si plein)
                    try:
                        self.rpm_queue.put_nowait(rpm)
                    except queue.Full:
                        try:
                            self.rpm_queue.get_nowait()
                            self.rpm_queue.put_nowait(rpm)
                        except queue.Empty:
                            pass
                except ValueError:
                    pass

            elif line.startswith("ACK:"):
                pass  # Accusé de réception, on peut le logger si besoin

            elif line.startswith("BOOT:"):
                print(f"[Serial] Arduino boot : {line}")
                self.status = "Connecté"

            elif line.startswith("FAILSAFE:"):
                print(f"[Serial] FAILSAFE activé sur l'Arduino !")
                self.status = "⚠ Failsafe"

            # Sortir de la boucle si plus rien à lire
            if self._serial.in_waiting == 0:
                break
