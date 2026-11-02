# Ikkanborduren

Ikkanborduren is a Dutch-language desktop app for designing machine embroidery.
It is built for the Bernina 540 and exports EXP and PES files. It is written in
Python with PySide6, and the interface and manual are in Dutch.

*Ikkanborduren is een Nederlandstalig borduurontwerpprogramma voor de Bernina 540
(EXP / PES). Zie [HANDLEIDING.html](HANDLEIDING.html) voor alle functies.*

## Features

- Convert drawings and logos into editable shapes: magic wand, or automatic
  digitising with one button.
- Fills: tatami, line-following satin (thin lines are always filled), satin
  fill, contour satin, running stitches (single, double, triple) and pattern
  fills.
- Several stitch-direction arrows per shape; click a part to highlight it and
  edit it directly.
- Grouping, a knife to split shapes, holes, overlap removal and lettering.
- Appliqué with placement and tack-down stops, and a border around the design.
- True-size hoops (Medium, Large Oval, Mega), stitch simulation, and fabric
  profiles that set density, pull compensation and underlay.

## Running it

```
pip install -r requirements.txt
python main.py
```

On Windows: `Installatie_Ikkanborduren.bat`, then `Start_Ikkanborduren.bat`
(see `START_HIER.txt`).

Tests: `QT_QPA_PLATFORM=offscreen python -m pytest`. Developer notes are in
`ONTWIKKELAAR.txt`.

## Disclaimer

This is an independent project. It is not affiliated with BERNINA, Hatch or
Wilcom and contains no code from them. It has not been tested on a physical
machine, so always do a test stitch-out first.

## License

[MIT](LICENSE)
