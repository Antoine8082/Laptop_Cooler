"""
controller.py — Moteur de régulation feedforward avec hystérésis et lissage.
"""


class CoolingController:
    """
    Calcule la consigne PWM en fonction de la télémétrie.
    
    Pipeline :
      1. temp_ref = max(cpu_temp, gpu_temp)
      2. pwm_base = interpolation linéaire sur la courbe (avec hystérésis)
      3. boost = boost_pwm si charge > seuil
      4. pwm_raw = min(pwm_base + boost, 100)
      5. pwm_smoothed = alpha * pwm_raw + (1 - alpha) * pwm_previous
      6. pwm_final = clamp(pwm_smoothed + overdrive, 0, max_pwm)
    """

    def __init__(self, config_manager):
        self._config = config_manager
        self._previous_pwm = 0.0
        self._hysteresis_state = "idle"  # "rising" ou "falling"
        self._last_base_pwm = 0.0

    def compute(self, telemetry_data):
        """
        Calcule le PWM cible à partir des données télémétrie.
        
        Args:
            telemetry_data: dict avec cpu_temp, gpu_temp, cpu_load, gpu_load
            
        Returns:
            float: PWM final (0-100)
        """
        cfg = self._config.get_all()

        cpu_temp = telemetry_data.get("cpu_temp", 0)
        gpu_temp = telemetry_data.get("gpu_temp", 0)
        cpu_load = telemetry_data.get("cpu_load", 0)
        gpu_load = telemetry_data.get("gpu_load", 0)

        # 1. Température de référence = max(CPU, GPU)
        temp_ref = max(cpu_temp, gpu_temp)

        # 2. Limite RPM → plafond PWM (calculé en premier car sert à scaler la courbe)
        max_rpm = cfg.get("max_rpm_limit", 28000)
        max_pwm = (max_rpm / 28000.0) * 100.0  # 100% courbe = max_rpm_limit

        # 3. Interpolation sur la courbe + mise à l'échelle + hystérésis
        # La courbe est en % relatif : 100% = max_pwm, 0% = 0%
        curve = sorted([(int(k), v) for k, v in cfg["curve"].items()])
        pwm_base_raw = self._interpolate_curve(curve, temp_ref) * (max_pwm / 100.0)
        pwm_base = self._apply_hysteresis(pwm_base_raw, cfg["hysteresis"])

        # 4. Feedforward : boost si charge élevée
        boost = 0
        load_threshold = cfg.get("load_threshold", 70)
        boost_pwm = cfg.get("boost_pwm", 15)
        if cpu_load > load_threshold or gpu_load > load_threshold:
            boost = boost_pwm

        # 5. PWM brut (plafonné à max_pwm)
        pwm_raw = min(pwm_base + boost, max_pwm)

        # 6. Lissage asymétrique : montée lente (alpha configuré), descente rapide (0.5 min)
        # Évite que le ventilateur reste haut après un pic de température (ex: boot Windows)
        alpha = cfg.get("alpha", 0.15)
        alpha = max(0.01, min(1.0, alpha))
        alpha_effective = alpha if pwm_raw >= self._previous_pwm else max(alpha, 0.5)
        pwm_smoothed = alpha_effective * pwm_raw + (1.0 - alpha_effective) * self._previous_pwm

        # 7. Overdrive + clamp final
        overdrive = cfg.get("overdrive", 0)
        pwm_final = max(0.0, min(pwm_smoothed + overdrive, max_pwm, 100.0))

        # Sauvegarder pour le prochain cycle
        self._previous_pwm = pwm_smoothed

        return round(pwm_final, 1)

    def notify_actual_pwm(self, value: float):
        """Synchronise l'état interne avec le PWM réellement envoyé à l'Arduino (plancher inclus)."""
        self._previous_pwm = float(value)
        self._last_base_pwm = min(self._last_base_pwm, float(value))

    def reset(self):
        """Réinitialise l'état interne du contrôleur."""
        self._previous_pwm = 0.0
        self._last_base_pwm = 0.0
        self._hysteresis_state = "idle"

    # ─── Méthodes privées ────────────────────────────────────────────────────

    @staticmethod
    def _interpolate_curve(curve, temp):
        """
        Interpolation linéaire sur la courbe de réponse.
        
        Args:
            curve: liste de tuples (temp, pwm) triée par temp croissante
            temp: température courante
            
        Returns:
            float: PWM interpolé
        """
        if not curve:
            return 0.0

        # Sous le premier point
        if temp <= curve[0][0]:
            return float(curve[0][1])

        # Au-dessus du dernier point
        if temp >= curve[-1][0]:
            return float(curve[-1][1])

        # Interpolation entre deux points
        for i in range(len(curve) - 1):
            t0, p0 = curve[i]
            t1, p1 = curve[i + 1]
            if t0 <= temp <= t1:
                if t1 == t0:
                    return float(p0)
                ratio = (temp - t0) / (t1 - t0)
                return p0 + ratio * (p1 - p0)

        return float(curve[-1][1])

    def _apply_hysteresis(self, pwm_target, hysteresis_deg):
        """
        Applique l'hystérésis : le PWM ne redescend que si l'écart est suffisant.
        
        On compare le PWM cible (basé sur la température) au dernier PWM de base.
        Si la différence est inférieure à un seuil proportionnel à l'hystérésis,
        on maintient la valeur précédente.
        """
        if hysteresis_deg <= 0:
            self._last_base_pwm = pwm_target
            return pwm_target

        # Seuil de changement : proportionnel à l'hystérésis (en °C → en % PWM)
        # ~2% PWM par °C d'hystérésis (sur une plage 40-90°C → 0-100% PWM)
        threshold = hysteresis_deg * 2.0

        diff = pwm_target - self._last_base_pwm

        if diff > threshold:
            # Montée significative → suivre (hystérésis évite les pics inutiles)
            self._last_base_pwm = pwm_target
            self._hysteresis_state = "rising"
        elif pwm_target < self._last_base_pwm:
            # Descente → toujours suivre immédiatement (le ventilateur doit pouvoir ralentir)
            self._last_base_pwm = pwm_target
            self._hysteresis_state = "falling"
        # else: montée inférieure au seuil → maintenir (bande morte)

        return self._last_base_pwm
