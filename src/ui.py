"""
ui.py — Fenêtre de réglages tkinter + tableau de bord temps réel.
"""

import tkinter as tk
from tkinter import ttk
import serial.tools.list_ports


# ─── Palette de couleurs ─────────────────────────────────────────────────────

COLORS = {
    "bg_dark":      "#1a1b2e",
    "bg_card":      "#242640",
    "bg_input":     "#2d2f4e",
    "accent":       "#00c7be",
    "accent_hover": "#00e6dc",
    "text":         "#e8e8f0",
    "text_dim":     "#8888a8",
    "green":        "#4cd964",
    "orange":       "#ff9f0a",
    "red":          "#ff3b30",
    "blue":         "#007aff",
    "border":       "#3a3c5c",
}

class ToolTip(object):
    """Crée une infobulle (tooltip) au survol d'un widget tkinter."""
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.widget.bind("<Enter>", self.enter)
        self.widget.bind("<Leave>", self.leave)
        self.tw = None

    def enter(self, event=None):
        if not self.text:
            return
        x, y, _, _ = self.widget.bbox("insert") or (0, 0, 0, 0)
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 20
        self.tw = tk.Toplevel(self.widget)
        self.tw.wm_overrideredirect(True)
        self.tw.wm_geometry(f"+{x}+{y}")
        
        # Style de l'infobulle assorti au thème sombre
        label = tk.Label(
            self.tw, text=self.text, justify='left',
            background=COLORS["bg_card"], foreground=COLORS["text"],
            relief='solid', borderwidth=1, highlightbackground=COLORS["border"],
            font=("Segoe UI", 9)
        )
        label.pack(ipadx=6, ipady=4)

    def leave(self, event=None):
        if self.tw:
            self.tw.destroy()
            self.tw = None


class SettingsWindow:
    """
    Fenêtre principale de réglages avec tableau de bord temps réel.
    """

    def __init__(self, root, config_manager, serial_manager, on_apply_callback, on_turbine_toggle=None, on_fixed_speed_toggle=None):
        self.root = root
        self._config = config_manager
        self._serial = serial_manager
        self._on_apply = on_apply_callback
        self._on_turbine_toggle = on_turbine_toggle
        self._on_fixed_speed_toggle = on_fixed_speed_toggle

        # Données temps réel (mises à jour par le main loop)
        self._telemetry = {"cpu_temp": 0, "gpu_temp": 0, "cpu_load": 0, "gpu_load": 0}
        self._current_pwm = 0
        self._current_rpm = 0

        # Variables tkinter
        self._vars = {}
        self._curve_vars = {}
        self._fixed_speed_enabled = False

        self._setup_window()
        self._build_ui()

        # Ajustement précis de la taille au contenu après la création des widgets
        self.root.update_idletasks()
        w = 580
        h = self.root.winfo_reqheight() + 10 # 10px de marge supplémentaire au cas où
        x = (self.root.winfo_screenwidth() - w) // 2
        y = (self.root.winfo_screenheight() - h) // 2
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def _setup_window(self):
        """Configure la fenêtre principale."""
        self.root.title("🌀 Laptop Cooler Control")
        self.root.configure(bg=COLORS["bg_dark"])
        self.root.resizable(False, False)

        # La taille et le centrage sont maintenant gérés après _build_ui

        # Style ttk
        style = ttk.Style()
        style.theme_use('clam')

        style.configure("Card.TFrame", background=COLORS["bg_card"])
        style.configure("Dark.TFrame", background=COLORS["bg_dark"])
        style.configure(
            "Title.TLabel",
            background=COLORS["bg_dark"],
            foreground=COLORS["accent"],
            font=("Segoe UI", 16, "bold"),
        )
        style.configure(
            "CardTitle.TLabel",
            background=COLORS["bg_card"],
            foreground=COLORS["accent"],
            font=("Segoe UI", 11, "bold"),
        )
        style.configure(
            "Value.TLabel",
            background=COLORS["bg_card"],
            foreground=COLORS["text"],
            font=("Consolas", 13, "bold"),
        )
        style.configure(
            "Unit.TLabel",
            background=COLORS["bg_card"],
            foreground=COLORS["text_dim"],
            font=("Segoe UI", 9),
        )
        style.configure(
            "Param.TLabel",
            background=COLORS["bg_card"],
            foreground=COLORS["text"],
            font=("Segoe UI", 10),
        )
        style.configure(
            "ParamValue.TLabel",
            background=COLORS["bg_card"],
            foreground=COLORS["accent"],
            font=("Consolas", 10, "bold"),
        )
        style.configure(
            "Status.TLabel",
            background=COLORS["bg_dark"],
            foreground=COLORS["text_dim"],
            font=("Segoe UI", 9),
        )
        style.configure(
            "Accent.TButton",
            font=("Segoe UI", 10, "bold"),
            padding=(20, 8),
        )
        style.configure(
            "Standard.TButton",
            font=("Segoe UI", 10),
            padding=(20, 8),
        )
        style.configure(
            "Small.TButton",
            padding=0,
        )
        style.configure(
            "TScale",
            background=COLORS["bg_card"],
            troughcolor=COLORS["bg_input"],
        )

    def _build_ui(self):
        """Construit tous les éléments de l'interface."""
        main_frame = ttk.Frame(self.root, style="Dark.TFrame")
        main_frame.pack(fill="both", expand=True, padx=16, pady=12)

        # ── Titre ──
        ttk.Label(main_frame, text="🌀 Laptop Cooler Control", style="Title.TLabel").pack(
            anchor="w", pady=(0, 12)
        )

        # ── Dashboard ──
        self._build_dashboard(main_frame)

        # ── Courbe de réponse ──
        self._build_curve_editor(main_frame)

        # ── Paramètres ──
        self._build_parameters(main_frame)

        # ── Barre de statut ──
        self._build_status_bar(main_frame)

        # ── Boutons ──
        self._build_buttons(main_frame)

    # ═════════════════════════════════════════════════════════════════════════
    #  DASHBOARD
    # ═════════════════════════════════════════════════════════════════════════

    def _build_dashboard(self, parent):
        """Tableau de bord temps réel."""
        card = ttk.Frame(parent, style="Card.TFrame")
        card.pack(fill="x", pady=(0, 10))
        inner = ttk.Frame(card, style="Card.TFrame")
        inner.pack(fill="x", padx=14, pady=10)

        ttk.Label(inner, text="📊 Tableau de Bord", style="CardTitle.TLabel").pack(anchor="w")

        # Grid de valeurs
        grid = ttk.Frame(inner, style="Card.TFrame")
        grid.pack(fill="x", pady=(8, 0))

        self._dash_labels = {}
        metrics = [
            ("cpu_temp", "T° CPU",  "°C", 0, 0),
            ("gpu_temp", "T° GPU",  "°C", 0, 1),
            ("cpu_load", "Load CPU", "%", 0, 2),
            ("gpu_load", "Load GPU", "%", 1, 0),
            ("pwm",      "PWM Cible", "%", 1, 1),
            ("rpm",      "Turbine", "RPM",  1, 2),
        ]

        for key, label, unit, row, col in metrics:
            cell = ttk.Frame(grid, style="Card.TFrame")
            cell.grid(row=row, column=col, padx=8, pady=4, sticky="w")

            ttk.Label(cell, text=label, style="Unit.TLabel").pack(anchor="w")
            val_frame = ttk.Frame(cell, style="Card.TFrame")
            val_frame.pack(anchor="w")

            val_label = ttk.Label(val_frame, text="--", style="Value.TLabel")
            val_label.pack(side="left")
            ttk.Label(val_frame, text=f" {unit}", style="Unit.TLabel").pack(side="left")

            self._dash_labels[key] = val_label

        # Colonnes équidistantes
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)
        grid.columnconfigure(2, weight=1)

    # ═════════════════════════════════════════════════════════════════════════
    #  COURBE DE RÉPONSE
    # ═════════════════════════════════════════════════════════════════════════

    def _build_curve_editor(self, parent):
        """Éditeur de la courbe de réponse (6 paliers, 40°C → 90°C)."""
        card = ttk.Frame(parent, style="Card.TFrame")
        card.pack(fill="x", pady=(0, 10))
        inner = ttk.Frame(card, style="Card.TFrame")
        inner.pack(fill="x", padx=14, pady=10)

        ttk.Label(inner, text="📈 Courbe de Réponse", style="CardTitle.TLabel").pack(anchor="w")

        curve = self._config.get("curve", {})

        for temp in [40, 50, 60, 70, 80, 90]:
            row = ttk.Frame(inner, style="Card.TFrame")
            row.pack(fill="x", pady=2)

            ttk.Label(row, text=f"{temp}°C", style="Param.TLabel", width=6).pack(side="left")

            var = tk.IntVar(value=int(curve.get(str(temp), 0)))
            self._curve_vars[temp] = var

            val_label = ttk.Label(row, text=f"{var.get():3d}%", style="ParamValue.TLabel", width=5)
            val_label.pack(side="right")

            slider = ttk.Scale(
                row, from_=0, to=100, orient="horizontal", variable=var,
                command=lambda v, lbl=val_label, vr=var: lbl.configure(text=f"{int(float(v)):3d}%"),
            )
            slider.pack(side="left", fill="x", expand=True, padx=(8, 8))

    # ═════════════════════════════════════════════════════════════════════════
    #  PARAMÈTRES
    # ═════════════════════════════════════════════════════════════════════════

    def _build_parameters(self, parent):
        """Curseurs de paramètres."""
        card = ttk.Frame(parent, style="Card.TFrame")
        card.pack(fill="x", pady=(0, 10))
        inner = ttk.Frame(card, style="Card.TFrame")
        inner.pack(fill="x", padx=14, pady=10)

        ttk.Label(inner, text="⚙ Paramètres", style="CardTitle.TLabel").pack(anchor="w")

        cfg = self._config.get_all()

        params = [
            ("hysteresis",     "Hystérésis (°C)",     2,    10,   cfg["hysteresis"],        1,    "°C", "Évite que la ventilation ne fasse le yoyo.\nNe ralentit que si la T° baisse de cette valeur."),
            ("alpha",          "Lissage (Alpha)",     0.01, 1.0,  cfg["alpha"],             0.01, "",   "Réactivité du ventilateur.\n1.0 = instantané, 0.01 = très progressif."),
            ("max_rpm_limit",  "Limite RPM Max",      0,    28000,cfg["max_rpm_limit"],    100,  "RPM", "Vitesse de rotation physique maximale à 100% PWM."),
            ("overdrive",      "Overdrive Manuel",    0,    30,   cfg["overdrive"],         1,    "%",   "Décalage fixe (%) ajouté inconditionnellement\nau ventilateur pour augmenter le refroidissement de manière globale."),
            ("load_threshold", "Seuil Charge (%)",    10,   100,  cfg["load_threshold"],    5,    "%",   "Seuil d'utilisation CPU/GPU (tâche lourde)\nau-delà duquel on applique immédiatement le Boost PWM."),
            ("boost_pwm",      "Boost PWM (%)",       0,    50,   cfg["boost_pwm"],         1,    "%",   "Coup de fouet. Puissance supplémentaire instantanée\najoutée dès que le 'Seuil Charge' est dépassé."),
            ("fixed_speed_pwm",  "Manuel (%)",          0,   100, cfg.get("fixed_speed_pwm", 10),   1,   "%",  "PWM cible en mode Manuel.\nLa courbe de réponse est ignorée.\nLe RPM réel est visible dans le tableau de bord."),
        ]

        for key, label, from_, to_, default, resolution, unit, tooltip_text in params:
            row = ttk.Frame(inner, style="Card.TFrame")
            row.pack(fill="x", pady=2)

            lbl = ttk.Label(row, text=label, style="Param.TLabel", width=18)
            lbl.pack(side="left")
            
            # Attacher l'infobulle au label
            if tooltip_text:
                ToolTip(lbl, tooltip_text)

            if isinstance(default, float):
                var = tk.DoubleVar(value=default)
            else:
                var = tk.IntVar(value=int(default))
            self._vars[key] = var

            display = f"{default}{' ' + unit if unit else ''}"
            val_label = ttk.Label(row, text=display, style="ParamValue.TLabel", width=10)
            val_label.pack(side="right")

            def make_update(v, lbl, u, is_float=False):
                def _update(val):
                    if is_float:
                        lbl.configure(text=f"{float(val):.2f}{' ' + u if u else ''}")
                    else:
                        lbl.configure(text=f"{int(float(val))}{' ' + u if u else ''}")
                return _update

            slider = ttk.Scale(
                row, from_=from_, to=to_, orient="horizontal", variable=var,
                command=make_update(var, val_label, unit, isinstance(default, float)),
            )
            slider.pack(side="left", fill="x", expand=True, padx=(8, 8))

    # ═════════════════════════════════════════════════════════════════════════
    #  BARRE DE STATUT
    # ═════════════════════════════════════════════════════════════════════════

    def _build_status_bar(self, parent):
        """Port série + indicateur de statut."""
        bar = ttk.Frame(parent, style="Dark.TFrame")
        bar.pack(fill="x", pady=(0, 8))

        # Port série
        ttk.Label(bar, text="Port Série :", style="Status.TLabel").pack(side="left")

        self._port_var = tk.StringVar(value=self._config.get("serial_port", "COM3"))
        ports = self._serial.list_ports()
        if not ports:
            ports = [self._port_var.get()]

        self._port_combo = ttk.Combobox(
            bar, textvariable=self._port_var, values=ports,
            width=8, state="readonly",
        )
        self._port_combo.pack(side="left", padx=(6, 16))

        # Bouton refresh ports
        refresh_btn = ttk.Button(bar, text="⟳", width=3, style="Small.TButton", command=self._refresh_ports)
        refresh_btn.pack(side="left", padx=(0, 16))

        # Statut
        ttk.Label(bar, text="Status :", style="Status.TLabel").pack(side="left")
        self._status_label = ttk.Label(bar, text="●  --", style="Status.TLabel")
        self._status_label.pack(side="left", padx=(4, 0))

        # Turbine toggle
        self._turbine_enabled = True
        self._turbine_btn = ttk.Button(
            bar, text="⏸ Turbine", width=12,
            command=self._toggle_turbine
        )
        self._turbine_btn.pack(side="left", padx=(20, 0))

        # Mode Manuel toggle
        self._fixed_speed_btn = ttk.Button(
            bar, text="📌 Manuel", width=12,
            command=self._toggle_fixed_speed
        )
        self._fixed_speed_btn.pack(side="left", padx=(8, 0))

    def _toggle_turbine(self):
        self._turbine_enabled = not self._turbine_enabled
        if self._turbine_enabled:
            self._turbine_btn.configure(text="⏸ Turbine")
        else:
            self._turbine_btn.configure(text="▶ Turbine")

        if self._on_turbine_toggle:
            self._on_turbine_toggle(self._turbine_enabled)

    def set_turbine_state(self, enabled):
        """Met à jour l'état du bouton depuis l'extérieur."""
        if self._turbine_enabled != enabled:
            self._turbine_enabled = enabled
            if enabled:
                self._turbine_btn.configure(text="⏸ Turbine")
            else:
                self._turbine_btn.configure(text="▶ Turbine")

    def _toggle_fixed_speed(self):
        self._fixed_speed_enabled = not self._fixed_speed_enabled
        if self._fixed_speed_enabled:
            self._fixed_speed_btn.configure(text="⏹ Manuel")
        else:
            self._fixed_speed_btn.configure(text="📌 Manuel")
        if self._on_fixed_speed_toggle:
            self._on_fixed_speed_toggle(self._fixed_speed_enabled)

    def set_fixed_speed_state(self, enabled):
        """Met à jour l'état du bouton depuis l'extérieur."""
        if self._fixed_speed_enabled != enabled:
            self._fixed_speed_enabled = enabled
            if enabled:
                self._fixed_speed_btn.configure(text="⏹ Manuel")
            else:
                self._fixed_speed_btn.configure(text="📌 Manuel")

    def _refresh_ports(self):
        """Rafraîchit la liste des ports COM."""
        ports = self._serial.list_ports()
        self._port_combo.configure(values=ports)

    # ═════════════════════════════════════════════════════════════════════════
    #  BOUTONS
    # ═════════════════════════════════════════════════════════════════════════

    def _build_buttons(self, parent):
        """Boutons Appliquer et Réduire."""
        btn_frame = ttk.Frame(parent, style="Dark.TFrame")
        btn_frame.pack(fill="x", pady=(4, 0))

        apply_btn = ttk.Button(
            btn_frame, text="✓  Appliquer", style="Accent.TButton",
            command=self._apply_settings,
        )
        apply_btn.pack(side="left", fill="x", expand=True, padx=(0, 5))

        minimize_btn = ttk.Button(
            btn_frame, text="▼  Réduire dans le Tray", style="Standard.TButton",
            command=self._minimize_to_tray,
        )
        minimize_btn.pack(side="left", fill="x", expand=True, padx=(5, 0))

    def _apply_settings(self):
        """Applique les réglages à la config et notifie le callback."""
        # Courbe
        new_curve = {}
        for temp, var in self._curve_vars.items():
            new_curve[str(temp)] = int(var.get())

        # Paramètres
        updates = {"curve": new_curve}
        for key, var in self._vars.items():
            updates[key] = var.get()

        # Port série
        new_port = self._port_var.get()
        updates["serial_port"] = new_port

        # Sauvegarder
        self._config.update(updates)

        # Notifier le main loop
        if self._on_apply:
            self._on_apply(updates)

    def _minimize_to_tray(self):
        """Cache la fenêtre (réduit dans le tray)."""
        self.root.withdraw()

    # ═════════════════════════════════════════════════════════════════════════
    #  MISE À JOUR TEMPS RÉEL
    # ═════════════════════════════════════════════════════════════════════════

    def update_dashboard(self, telemetry, pwm, rpm):
        """
        Met à jour le tableau de bord avec les données temps réel.
        Appelé depuis le main loop via root.after().
        """
        self._telemetry = telemetry
        self._current_pwm = pwm
        self._current_rpm = rpm

        # Températures avec coloration
        cpu_t = telemetry.get("cpu_temp", 0)
        gpu_t = telemetry.get("gpu_temp", 0)

        self._dash_labels["cpu_temp"].configure(text=f"{cpu_t:.0f}")
        self._dash_labels["gpu_temp"].configure(text=f"{gpu_t:.0f}")
        self._dash_labels["cpu_load"].configure(text=f"{telemetry.get('cpu_load', 0):.0f}")
        self._dash_labels["gpu_load"].configure(text=f"{telemetry.get('gpu_load', 0):.0f}")
        self._dash_labels["pwm"].configure(text=f"{pwm:.0f}")
        self._dash_labels["rpm"].configure(text=f"{rpm}")

        # Colorer les températures
        for key, val in [("cpu_temp", cpu_t), ("gpu_temp", gpu_t)]:
            if val >= 85:
                color = COLORS["red"]
            elif val >= 70:
                color = COLORS["orange"]
            elif val > 0:
                color = COLORS["green"]
            else:
                color = COLORS["text"]

            style_name = f"{key}.Value.TLabel"
            style = ttk.Style()
            style.configure(style_name, foreground=color, background=COLORS["bg_card"],
                            font=("Consolas", 13, "bold"))
            self._dash_labels[key].configure(style=style_name)

    def update_status(self, status_text, connected=False):
        """Met à jour l'indicateur de statut série."""
        if connected:
            self._status_label.configure(text=f"●  {status_text}")
            # Vert
            s = ttk.Style()
            s.configure("Connected.Status.TLabel", foreground=COLORS["green"],
                        background=COLORS["bg_dark"], font=("Segoe UI", 9))
            self._status_label.configure(style="Connected.Status.TLabel")
        else:
            self._status_label.configure(text=f"○  {status_text}")
            s = ttk.Style()
            s.configure("Disconnected.Status.TLabel", foreground=COLORS["red"],
                        background=COLORS["bg_dark"], font=("Segoe UI", 9))
            self._status_label.configure(style="Disconnected.Status.TLabel")

    def show(self):
        """Affiche la fenêtre."""
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def hide(self):
        """Cache la fenêtre."""
        self.root.withdraw()
