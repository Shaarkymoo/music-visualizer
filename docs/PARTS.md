# Parts List (BOM)

Consolidated build of materials for the wall LED visualizer. Merged from the
earlier `hardware.txt` / `stuff.txt` lists (duplicates collapsed).

| Part | Spec | Qty | Role / Notes |
|---|---|---|---|
| Mean Well LRS-350-5 | 300 W / 60 A / 5 V SMPS | 1 | Main power supply |
| CJMCU 64-bit 8x8 RGB LED driver board | WS2812B ×64, 5 V, ~60 mA/LED peak | 8 | Display panels (8×8 each = 512 LEDs total); SKU 43121 |
| ESP32 dev board | SquadPixel ESP-WROOM-32, silkscreen D-labeled pins | 1 | Receiver / display driver |
| SN74AHCT125N | Quad buffer, DIP-14, 5 V VCC | 2 | Level shifter (3.3 V → 5 V data); SKU R213464 |
| 14-pin DIP IC socket | DIP-14 | 2 | Level shifter sockets; SKU 499375 |
| URS1E102MHD1TO (Nichicon) | 1000 µF 25 V ±20% electrolytic, 830 mA@120 Hz | 5 | PSU output smoothing across the LED branches; SKU R253108 |
| 100 nF 50 V disc capacitor | Disc ceramic | 1 | — (spare) |
| BK/ATC-10 (EATON BUSSMANN) | Blade fuse, 10 A, 32 V, fast-acting | 5 | Per-branch LED power fusing; SKU R123147 |
| Waterproof inline blade fuse with holders | — | 1 set (5 pcs) | Fuse holders; SKU 699636 |
| 0287030.PXCN (LittleFuse) | Blade fuse, 30 A, 32 V, automotive | 1 | Main power-line fuse (30 A total) |
| MFR50SFTE52-300R (YAGEO) | 300 Ω 0.5 W axial resistor | 6 | Data-line protection (unused so far); SKU R202958 |
| 18 AWG silicone wire, yellow | — | 5 | Power (PSU 5 V branches); SKU R150521 |
| 22 AWG silicone wire, black | — | 5 | GND wiring; SKU 1824995 |
| 22 AWG high-voltage silicone wire, red | 3000 V rated | 5 | Signal / high-voltage wiring; SKU R257303 |
| Plusivo Basic Soldering Kit | 230 V (EU) | 1 | Tools; SKU 835827 |
