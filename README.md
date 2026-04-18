# 🌀 Laptop Cooler

Système de refroidissement DIY en boucle fermée pour laptop — blower centrifuge 24V piloté par Arduino Nano, régulé par télémétrie CPU/GPU en temps réel.

## Architecture

```
┌──────────────┐     USB/Série      ┌─────────────────┐     PWM 25kHz     ┌──────────────┐
│   PC Windows │ ◄──────────────► │  Arduino Nano   │ ──────────────► │  Driver 24V  │
│              │   PWM:xx / RPM:xx  │  (D9=PWM,D8=EN) │                  │  + Blower    │
│  Python App  │                    │  (D2=Tacho/FG)  │ ◄─────────────   │  28000 RPM   │
│  + LHM DLL   │                    └─────────────────┘   Signal FG       └──────────────┘
└──────────────┘
```

## Fonctionnalités

- **Télémétrie temps réel** : T° et charge CPU/GPU via LibreHardwareMonitor
- **Régulation feedforward** : courbe de réponse paramétrable (40°C→90°C) + boost sur charge élevée
- **Lissage exponentiel** : filtre passe-bas sur le PWM pour des transitions douces
- **Hystérésis** : évite les oscillations autour des seuils
- **System Tray** : tourne silencieusement en tâche de fond avec icône dynamique
- **Failsafe Arduino** : coupe le moteur après 5s sans commande
- **PWM 25 kHz** : inaudible, via Timer1 du Nano

## Prérequis

### Matériel
- Arduino Nano (ATmega328P)
- Blower centrifuge 24V avec sortie tachymétrique (FG)
- Driver moteur compatible PWM

### Logiciel
- Python 3.10+ (x64)
- Arduino IDE
- `LibreHardwareMonitorLib.dll` → dossier `DLL/`

## Installation

### 1. Firmware Arduino
1. Ouvrir `arduino/blower_controller.ino` dans l'Arduino IDE
2. Vérifier `PULSES_PER_REV = 3` (ajuster selon votre moteur)
3. Upload sur le Nano

### 2. Application Python (développement)
```bash
pip install -r requirements.txt
python src/laptop_cooler.py
```
> ⚠️ **Lancer en administrateur** pour accéder aux capteurs de température.

### 3. Build de l'exécutable
```bash
pyinstaller laptop_cooler.spec
```
L'exécutable sera dans `dist/Laptop_Cooler.exe`.

### 4. Auto-démarrage sans UAC
1. Copier `Laptop_Cooler.exe` dans le dossier de votre choix
2. Copier `install_scheduled_task.bat` dans le même dossier
3. Clic droit sur `install_scheduled_task.bat` → **Exécuter en tant qu'administrateur**
4. L'application se lancera automatiquement à chaque login, sans invite UAC

Pour désinstaller : exécuter `uninstall_scheduled_task.bat` en administrateur.

## Structure du Projet

```
Laptop_Cooler/
├── arduino/
│   └── blower_controller.ino      # Firmware Arduino Nano
├── src/
│   ├── laptop_cooler.py           # Point d'entrée principal
│   ├── config_manager.py          # Gestion config.json
│   ├── telemetry.py               # Lecture CPU/GPU (LibreHardwareMonitor)
│   ├── serial_comm.py             # Communication série Arduino
│   ├── controller.py              # Régulation feedforward
│   ├── tray_app.py                # System Tray (pystray)
│   └── ui.py                      # Fenêtre tkinter
├── assets/
│   └── icon.ico                   # Icône application
├── DLL/
│   └── LibreHardwareMonitorLib.dll
├── config.json                    # Configuration persistante
├── requirements.txt               # Dépendances Python
├── laptop_cooler.spec             # Spec PyInstaller
├── install_scheduled_task.bat     # Installation tâche planifiée
└── uninstall_scheduled_task.bat   # Désinstallation tâche planifiée
```

## Protocole Série

| Direction | Format | Exemple | Description |
|-----------|--------|---------|-------------|
| PC → Arduino | `PWM:xx\n` | `PWM:75\n` | Consigne 0-100% |
| Arduino → PC | `RPM:xxxxx\n` | `RPM:14500\n` | Vitesse réelle (toutes les 500ms) |
| Arduino → PC | `ACK:xx\n` | `ACK:75\n` | Accusé de réception |
| Arduino → PC | `FAILSAFE:ACTIVE\n` | — | Timeout 5s déclenché |

## Configuration (`config.json`)

| Paramètre | Défaut | Description |
|-----------|--------|-------------|
| `serial_port` | `COM3` | Port série Arduino |
| `curve` | 40°→0%, 90°→100% | Courbe de réponse (6 paliers) |
| `hysteresis` | 3°C | Bande morte anti-oscillation |
| `alpha` | 0.15 | Constante de lissage (0=lent, 1=instantané) |
| `max_rpm_limit` | 28000 | Limite RPM maximale |
| `overdrive` | 0% | Boost PWM manuel permanent |
| `load_threshold` | 70% | Seuil de charge pour le boost |
| `boost_pwm` | 15% | Boost PWM sur charge élevée |

## Licence

Projet personnel — usage privé.
