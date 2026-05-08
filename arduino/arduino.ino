/*
 * ============================================================================
 *  Laptop Cooler — Arduino Nano Firmware
 * ============================================================================
 *  Pilote un blower centrifuge 24V via un driver externe.
 *
 *  Brochage :
 *    D9  → PWM (sortie vers driver, 10 kHz via Timer1)
 *    D8  → Enable (INPUT/flottant = moteur actif, OUTPUT LOW/GND = moteur coupé)
 *    D2  → Tachymètre / FG (entrée interruption INT0, INPUT_PULLUP)
 *
 *  Protocole Série (115200 bauds) :
 *    Réception :  "PWM:xx\n"   où xx = 0..100 (pourcentage)
 *    Émission  :  "RPM:xxxxx\n" toutes les 500 ms
 * ============================================================================
 */

// ─── Configuration ──────────────────────────────────────────────────────────

const byte PIN_PWM    = 9;    // OC1A — Timer1 PWM output
const byte PIN_ENABLE = 8;    // Enable / Disable du driver
const byte PIN_TACHO  = 2;    // Tachymètre FG (INT0)

const unsigned int PULSES_PER_REV   = 2;    // Impulsions par tour (moteur 4 pôles = 2 paires de pôles)
const unsigned long RPM_INTERVAL_MS = 500;  // Intervalle de calcul RPM (ms)
const unsigned long SERIAL_BAUD     = 115200;

// ─── Variables globales ─────────────────────────────────────────────────────

volatile unsigned long pulseCount = 0;  // Compteur d'impulsions (modifié dans ISR)

unsigned long lastRpmTime = 0;      // Dernier calcul RPM
unsigned long currentRPM  = 0;     // RPM calculé
byte          currentPWM  = 0;     // Consigne PWM courante (0-100)
bool motorEnabled = false;          // État du moteur

const byte SERIAL_BUF_SIZE = 32;
char serialBuffer[SERIAL_BUF_SIZE]; // Buffer de réception série (char[] fixe, pas de heap)
byte serialBufLen = 0;

// ─── Setup ──────────────────────────────────────────────────────────────────

void setup() {
  // --- Pins ---
  // EN : open-drain — LOW (GND) = stop, INPUT (flottant) = run
  digitalWrite(PIN_ENABLE, LOW);
  pinMode(PIN_ENABLE, OUTPUT);   // Moteur coupé au démarrage

  // Tachymètre : INPUT_PULLUP obligatoire (sortie collecteur ouvert du driver)
  pinMode(PIN_TACHO, INPUT_PULLUP);

  // --- Timer1 : Fast PWM 10 kHz sur Pin D9 (OC1A) ---
  // Mode 14 : Fast PWM, TOP = ICR1
  // Prescaler = 1 (CS10)
  // f_PWM = F_CPU / (1 * (1 + ICR1)) = 16 000 000 / (1 * 1600) = 10 000 Hz
  pinMode(PIN_PWM, OUTPUT);

  TCCR1A = 0;  // Reset
  TCCR1B = 0;  // Reset

  // COM1A1 : Clear OC1A on Compare Match, set at BOTTOM (non-inverting)
  // WGM11  : Part of Mode 14 (Fast PWM, TOP = ICR1)
  TCCR1A = (1 << COM1A1) | (1 << WGM11);

  // WGM13, WGM12 : Part of Mode 14
  // CS10 : Prescaler = 1 (no prescaling)
  TCCR1B = (1 << WGM13) | (1 << WGM12) | (1 << CS10);

  // TOP = 1599 → 16 MHz / (1 * (1 + 1599)) = 10 kHz
  ICR1  = 1599;

  // Duty cycle initial = 0%
  OCR1A = 0;

  // --- Interruption tachymètre ---
  attachInterrupt(digitalPinToInterrupt(PIN_TACHO), tachISR, RISING);

  // --- Série ---
  Serial.begin(SERIAL_BAUD);

  lastRpmTime = millis();

  Serial.println("BOOT:OK");
}

// ─── Boucle principale ─────────────────────────────────────────────────────

void loop() {
  unsigned long now = millis();

  // --- 1. Lecture des commandes série ---
  readSerialCommands();

  // --- 2. Calcul RPM toutes les RPM_INTERVAL_MS ---
  if (now - lastRpmTime >= RPM_INTERVAL_MS) {
    unsigned long elapsed = now - lastRpmTime;

    // Lecture atomique du compteur
    noInterrupts();
    unsigned long counts = pulseCount;
    pulseCount = 0;
    interrupts();

    // RPM = (impulsions / impulsions_par_tour) * (60000 / elapsed_ms)
    if (elapsed > 0 && PULSES_PER_REV > 0) {
      currentRPM = (counts * 60000UL) / ((unsigned long)PULSES_PER_REV * elapsed);
    } else {
      currentRPM = 0;
    }

    lastRpmTime = now;

    // Envoi des RPM au PC
    Serial.print("RPM:");
    Serial.println(currentRPM);
  }
}

// ─── ISR Tachymètre ────────────────────────────────────────────────────────

void tachISR() {
  pulseCount++;
}

// ─── Lecture commandes série ────────────────────────────────────────────────

void readSerialCommands() {
  while (Serial.available() > 0) {
    char c = Serial.read();

    if (c == '\n' || c == '\r') {
      if (serialBufLen > 0) {
        serialBuffer[serialBufLen] = '\0';
        processCommand(serialBuffer);
        serialBufLen = 0;
      }
    } else {
      if (serialBufLen < SERIAL_BUF_SIZE - 1) {
        serialBuffer[serialBufLen++] = c;
      }
    }
  }
}

// ─── Traitement d'une commande ──────────────────────────────────────────────

void processCommand(const char *cmd) {
  // Format attendu : "PWM:xx" où xx = 0..100
  if (strncmp(cmd, "PWM:", 4) == 0) {
    int value = atoi(cmd + 4);

    // Validation de la plage
    if (value < 0)   value = 0;
    if (value > 100) value = 100;

    currentPWM = (byte)value;

    if (value > 0) {
      setMotor(value, true);
    } else {
      setMotor(0, false);
    }

    // Accusé de réception
    Serial.print("ACK:");
    Serial.println(value);
  }
}

// ─── Contrôle moteur ────────────────────────────────────────────────────────

// Seuil minimum en valeur Timer1 directe (résolution 3.1 mV/step, VSR 0-5V).
// Formule : V / 5.0 * 1599.  Ex : 0.30V→96  0.31V→99  0.32V→102  0.33V→106  0.35V→112
const unsigned int MIN_DUTY = 109;  // 0.34V

void setMotor(byte pwmPercent, bool enable) {
  motorEnabled = enable;

  // EN open-drain : INPUT (flottant) = déconnecté de GND = Run
  //                 OUTPUT LOW (GND) = Stop
  if (enable) {
    pinMode(PIN_ENABLE, INPUT);
  } else {
    pinMode(PIN_ENABLE, OUTPUT);
    digitalWrite(PIN_ENABLE, LOW);
  }

  // Conversion 0-100% → 0-1599, plancher MIN_DUTY appliqué après
  unsigned int duty = 0;
  if (enable && pwmPercent > 0) {
    duty = (unsigned int)map(pwmPercent, 0, 100, 0, 1599);
    if (duty < MIN_DUTY) duty = MIN_DUTY;
  }

  OCR1A = duty;
}
