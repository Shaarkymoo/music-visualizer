# Hardware Notes

Consolidated reference for the LED wall. Distilled from the original
`SOFTWARE_NOTES.md` (superseded) — covers wiring, level shifter, fusing, power,
panel orientation, and the current data path.

## System overview / data path

- **Python does ALL audio/visual processing.** Only raw RGB pixel data is sent
  to the ESP32; the ESP32 is a dumb display — it just receives and shows.
- **USB serial is the current primary path.** UDP broadcast exists in the code
  but is dormant / future work.

## Wiring (verified with multimeter + working sweep)

```
ESP32 D4 ──── level shifter pin 2 (1A)  ── input
level shifter pin 3 (1Y) ────────────── first board DIN
board DOUT ── next board DIN ── ... (serpentine chain through all 8 panels)
```

- PSU 5 V feeds LED branches via per-branch 10 A fuses, and the level shifter
  VCC (pin 14) directly — not through the ESP32 branch.
- PSU GND ties to a common rail: ESP32 GND, level shifter GND (pin 7), and every
  LED board GND.
- **Color order: GRB** (FastLED `COLOR_ORDER GRB`).
- **Grid: 16 rows × 32 cols = 512 LEDs** (8 panels × 64 LEDs). Python renders
  the same 32×16.

## Level shifter (SN74AHCT125N) — critical facts

| Pin | Function | Connection |
|---|---|---|
| 1, 4, 10, 13 | OE (output enable, **ACTIVE LOW**) | **ALL tied to GND** — floating = silent dead data line |
| 2 (1A) | channel 1 input | ESP32 D4 |
| 3 (1Y) | channel 1 output | first board DIN |
| 5, 9, 12 (2A/3A/4A) | unused channel inputs | tied to GND (good practice) |
| 7 | GND | common ground |
| 14 | VCC | PSU 5 V |

## ESP32 board facts

- **D4 = GPIO4** — confirmed by board silkscreen ("GPIO4" printed next to D4).
  Do NOT assume NodeMCU-32S mapping (where D4=GPIO14); this board is D=GPIO.
- `LED_BUILTIN` = GPIO2 (used for alive-blink in normal mode).
- ESP32 is a **clone** — silkscreen D-labels; verify any new pin against silkscreen.
- The old Wokwi `diagram.json` was simulation-only and out of date — deleted.
  Do not trust it for real wiring.

## Fusing

- **10 A per LED branch** (BK/ATC-10 blade fuses).
- **30 A total on the main power line** (LittleFuse 0287030.PXCN, 32 V).
- **~1 A slow-blow** for the ESP32 branch if PSU-powered (a 5 A fuse melted at
  power-on — inrush/transient; the ESP32 only draws ~0.5 A). **USB power is
  preferred during development** (removes the fuse/PSU variable entirely;
  laptop USB is current-limited).
- **25 A current limiter in firmware** protects the 30 A fuse (see below).

## Power

- Mean Well **LRS-350-5**: 300 W / 60 A / 5 V SMPS.
- **1000 µF caps installed across the PSU output** near the LED branches
  (smooths inrush/ripple).
- Fuses + level shifter run warm under load — normal. Hot (can't hold 3 s) = problem.

## Panel orientation

- **Columns 2 and 4 are physically upside down** (panels rotated 180° in the
  serpentine chain to keep DIN→DOUT flowing). This is a **wiring fact, not a
  defect — do not "fix" the wiring.**
- Remapped in **Python** (`python/pack.py` REMAP table) — keeps the ESP32 dumb
  and the on-screen grid the single source of truth.

## 25 A power limiter (firmware)

```
I_frame = Σ((R+G+B)/255) * 20mA        # estimated frame current
if I_frame > 25A:  scale RGB by 25A / I_frame
```

Peak frame current is ~30.7 A, so the limiter keeps the draw under the 30 A
fuse rating.

## Historical note

The UDP / WiFi design documented in the old `SOFTWARE_NOTES.md` (UDP broadcast
at 30–60 fps, DHCP-assigned IP, stale-frame sequence numbers, etc.) is
superseded: the current design uses **USB serial as the primary path**.
