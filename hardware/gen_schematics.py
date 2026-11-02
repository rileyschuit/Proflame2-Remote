#!/usr/bin/env python3
"""Writes the two KiCad schematics. Edit this file, not the .kicad_sch output.

Boards are drawn as blocks with a net label on each pin, which reads like the
wiring table in docs/wiring.md. Symbols are embedded in each schematic.
"""
import pathlib
import uuid

OUT = pathlib.Path(__file__).parent
NAMESPACE = uuid.UUID("6f0a7a7e-6d3b-4c52-9d0e-3a8f2b1c7d10")
PIN_LEN = 2.54
PITCH = 2.54


def grid(value):
    """Snaps to KiCad's 1.27 mm connection grid."""
    return round(round(value / 1.27) * 1.27, 2)


def uid(*parts):
    return str(uuid.uuid5(NAMESPACE, "/".join(str(p) for p in parts)))


def text(value):
    return '"' + value.replace('"', '\\"') + '"'


class Block:
    """A rectangular symbol. Pins are (number, name, type), None leaves a gap."""

    def __init__(self, lib_id, left, right, width=30.48):
        self.lib_id, self.left, self.right, self.width = lib_id, left, right, width
        rows = max(len(left), len(right))
        self.height = (rows + 1) * PITCH

    def pin_positions(self):
        """Yields (pin, side, x, y) relative to the symbol origin, y up."""
        half = self.width / 2
        top = self.height / 2 - PITCH
        for side, pins, x in (("L", self.left, -half - PIN_LEN), ("R", self.right, half + PIN_LEN)):
            for row, pin in enumerate(pins):
                if pin:
                    yield pin, side, x, round(top - row * PITCH, 2)

    def symbol(self):
        name = self.lib_id.split(":")[1]
        half_w, half_h = self.width / 2, self.height / 2
        pins = []
        for (number, pin_name, kind), side, x, y in self.pin_positions():
            angle = 0 if side == "L" else 180
            pins.append(
                f'(pin {kind} line (at {x} {y} {angle}) (length {PIN_LEN})'
                f' (name {text(pin_name)} (effects (font (size 1.27 1.27))))'
                f' (number {text(number)} (effects (font (size 1.27 1.27)))))'
            )
        return f'''(symbol {text(self.lib_id)} (in_bom yes) (on_board yes)
  (property "Reference" "U" (at 0 {half_h + 1.27} 0) (effects (font (size 1.27 1.27))))
  (property "Value" {text(name)} (at 0 {-half_h - 1.27} 0) (effects (font (size 1.27 1.27))))
  (property "Footprint" "" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))
  (property "Datasheet" "" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))
  (symbol "{name}_0_1" (rectangle (start {-half_w} {half_h}) (end {half_w} {-half_h})
    (stroke (width 0.254) (type default)) (fill (type background))))
  (symbol "{name}_1_1" {" ".join(pins)}))'''


CAP = '''(symbol "proflame:C" (pin_numbers hide) (pin_names (offset 0.254) hide) (in_bom yes) (on_board yes)
  (property "Reference" "C" (at 2.54 1.27 0) (effects (font (size 1.27 1.27)) (justify left)))
  (property "Value" "C" (at 2.54 -1.27 0) (effects (font (size 1.27 1.27)) (justify left)))
  (property "Footprint" "" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))
  (property "Datasheet" "" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))
  (symbol "C_0_1"
    (polyline (pts (xy -2.032 0.762) (xy 2.032 0.762)) (stroke (width 0.508) (type default)) (fill (type none)))
    (polyline (pts (xy -2.032 -0.762) (xy 2.032 -0.762)) (stroke (width 0.508) (type default)) (fill (type none))))
  (symbol "C_1_1"
    (pin passive line (at 0 3.81 270) (length 3.048) (name "~" (effects (font (size 1.27 1.27)))) (number "1" (effects (font (size 1.27 1.27)))))
    (pin passive line (at 0 -3.81 90) (length 3.048) (name "~" (effects (font (size 1.27 1.27)))) (number "2" (effects (font (size 1.27 1.27)))))))'''

CC1101 = Block(
    "proflame:CC1101_Module",
    [("1", "VCC", "power_in"), ("2", "GND", "power_in"), ("3", "CSN", "input"),
     ("4", "SCK", "input"), ("5", "MOSI", "input"), ("6", "MISO", "output"),
     ("7", "GDO0", "bidirectional"), ("8", "GDO2", "bidirectional")],
    [("9", "ANT", "passive")],
)

ANTENNA = Block("proflame:Antenna_315MHz", [("1", "RF", "passive")], [], width=12.7)

XIAO = Block(
    "proflame:XIAO_ESP32S3",
    [("1", "D0/GPIO1", "bidirectional"), ("2", "D1/GPIO2", "bidirectional"),
     ("3", "D2/GPIO3", "bidirectional"), ("4", "D3/GPIO4", "bidirectional"),
     ("5", "D4/GPIO5", "bidirectional"), ("6", "D5/GPIO6", "bidirectional"),
     ("7", "D6/GPIO43", "bidirectional")],
    [("14", "5V", "passive"), ("13", "GND", "power_out"), ("12", "3V3", "power_out"),
     ("11", "D10/GPIO9", "output"), ("10", "D9/GPIO8", "input"), ("9", "D8/GPIO7", "output"),
     ("8", "D7/GPIO44", "bidirectional")],
)

UNO = Block(
    "proflame:Arduino_UNO_R3",
    [("1", "5V", "power_out"), ("2", "3V3", "power_out"), ("3", "GND", "power_out"),
     ("4", "USB", "passive")],
    [("5", "D13/SCK", "output"), ("6", "D12/MISO", "input"), ("7", "D11/MOSI", "output"),
     ("8", "D10/SS", "output")],
)

SHIFTER = Block(
    "proflame:BSS138_Level_Shifter_4ch",
    [("1", "HV", "power_in"), ("2", "GND", "power_in"), ("3", "HV1", "bidirectional"),
     ("4", "HV2", "bidirectional"), ("5", "HV3", "bidirectional"), ("6", "HV4", "bidirectional")],
    [("7", "LV", "power_in"), ("8", "GND", "power_in"), ("9", "LV1", "bidirectional"),
     ("10", "LV2", "bidirectional"), ("11", "LV3", "bidirectional"), ("12", "LV4", "bidirectional")],
)


class Sheet:
    def __init__(self, filename, title, comments):
        self.filename, self.title, self.comments = filename, title, comments
        self.symbols, self.instances, self.labels, self.no_connects, self.notes = {}, [], [], [], []

    def place_block(self, block, reference, value, x, y, nets):
        x, y = grid(x), grid(y)
        self.symbols[block.lib_id] = block.symbol()
        pin_ids = []
        half_h = block.height / 2
        for pin, side, px, py in block.pin_positions():
            number = pin[0]
            sx, sy = round(x + px, 2), round(y - py, 2)
            pin_ids.append(number)
            net = nets.get(number)
            if net:
                self.labels.append((net, sx, sy, 180 if side == "L" else 0))
            else:
                self.no_connects.append((sx, sy))
        self.instances.append(
            f'''(symbol (lib_id {text(block.lib_id)}) (at {x} {y} 0) (unit 1) (in_bom yes) (on_board yes) (dnp no)
  (uuid {text(uid(self.filename, reference))})
  (property "Reference" {text(reference)} (at {x} {y - half_h - 1.27} 0) (effects (font (size 1.27 1.27))))
  (property "Value" {text(value)} (at {x} {y + half_h + 1.27} 0) (effects (font (size 1.27 1.27))))
  (property "Footprint" "" (at {x} {y} 0) (effects (font (size 1.27 1.27)) hide))
  (property "Datasheet" "" (at {x} {y} 0) (effects (font (size 1.27 1.27)) hide))
  {" ".join(f'(pin {text(n)} (uuid {text(uid(self.filename, reference, n))}))' for n in pin_ids)}
  (instances (project {text(self.filename)} (path {text("/" + uid(self.filename))} (reference {text(reference)}) (unit 1)))))'''
        )

    def place_cap(self, reference, value, x, y, top_net, bottom_net):
        x, y = grid(x), grid(y)
        self.symbols["proflame:C"] = CAP
        self.labels.append((top_net, x, round(y - 3.81, 2), 90))
        self.labels.append((bottom_net, x, round(y + 3.81, 2), 270))
        self.instances.append(
            f'''(symbol (lib_id "proflame:C") (at {x} {y} 0) (unit 1) (in_bom yes) (on_board yes) (dnp no)
  (uuid {text(uid(self.filename, reference))})
  (property "Reference" {text(reference)} (at {x + 2.54} {y - 1.27} 0) (effects (font (size 1.27 1.27)) (justify left)))
  (property "Value" {text(value)} (at {x + 2.54} {y + 1.27} 0) (effects (font (size 1.27 1.27)) (justify left)))
  (property "Footprint" "" (at {x} {y} 0) (effects (font (size 1.27 1.27)) hide))
  (property "Datasheet" "" (at {x} {y} 0) (effects (font (size 1.27 1.27)) hide))
  (pin "1" (uuid {text(uid(self.filename, reference, 1))})) (pin "2" (uuid {text(uid(self.filename, reference, 2))}))
  (instances (project {text(self.filename)} (path {text("/" + uid(self.filename))} (reference {text(reference)}) (unit 1)))))'''
        )

    def note(self, value, x, y):
        x, y = grid(x), grid(y)
        self.notes.append((value, x, y))

    def write(self):
        comments = " ".join(f'(comment {i + 1} {text(c)})' for i, c in enumerate(self.comments))
        parts = [
            '(kicad_sch (version 20250114) (generator "gen_schematics") (generator_version "9.0")',
            f'(uuid {text(uid(self.filename))})',
            '(paper "A4")',
            f'(title_block (title {text(self.title)}) (rev "0.1") (company "rileyschuit/Proflame2-Remote") {comments})',
            "(lib_symbols " + "\n".join(self.symbols.values()) + ")",
        ]
        for net, x, y, angle in self.labels:
            justify = "left" if angle in (0, 90) else "right"
            parts.append(
                f'(label {text(net)} (at {x} {y} {angle}) (effects (font (size 1.27 1.27)) (justify {justify} bottom))'
                f' (uuid {text(uid(self.filename, "label", net, x, y))}))'
            )
        for x, y in self.no_connects:
            parts.append(f'(no_connect (at {x} {y}) (uuid {text(uid(self.filename, "nc", x, y))}))')
        for value, x, y in self.notes:
            parts.append(
                f'(text {text(value)} (exclude_from_sim no) (at {x} {y} 0) (effects (font (size 1.27 1.27)) (justify left))'
                f' (uuid {text(uid(self.filename, "note", x, y))}))'
            )
        parts.extend(self.instances)
        parts.append(f'(sheet_instances (path "/" (page "1")))')
        parts.append(")")
        (OUT / f"{self.filename}.kicad_sch").write_text("\n".join(parts) + "\n")


def esp32():
    sheet = Sheet("esp32s3_cc1101", "ESP32-S3 + CC1101 fireplace remote (serial, MQTT, REST)",
                  ["Serial over USB-C, MQTT and REST over Wi-Fi. Not yet built."])
    sheet.place_block(XIAO, "U1", "Seeed XIAO ESP32-S3", 80, 80, {
        "2": "GDO0", "1": "GDO2", "4": "CSN", "9": "SCK", "10": "MISO", "11": "MOSI",
        "12": "+3V3", "13": "GND",
    })
    sheet.place_block(CC1101, "U2", "CC1101 module, 315 MHz", 190, 80, {
        "1": "+3V3", "2": "GND", "3": "CSN", "4": "SCK", "5": "MOSI", "6": "MISO",
        "7": "GDO0", "8": "GDO2", "9": "ANT",
    })
    sheet.place_block(ANTENNA, "AE1", "315 MHz antenna", 245, 80, {"1": "ANT"})
    sheet.place_cap("C1", "100nF", 150, 125, "+3V3", "GND")
    sheet.place_cap("C2", "10uF", 175, 125, "+3V3", "GND")
    sheet.note("Put C1 and C2 at the CC1101 VCC and GND pins.", 40, 115)
    sheet.note("ANT: 315 MHz antenna, or a 23.8 cm wire on modules with a solder pad.", 40, 120)
    sheet.note("CC1101 is 3.3 V only. Check the pin order against your module's silkscreen.", 40, 125)
    sheet.note("GDO0 and GDO2 are unused by the current sketches; wired for listening to the real remote.", 40, 130)
    sheet.note("USB-C powers the board and carries the serial console. Fit the Wi-Fi antenna the XIAO ships with.", 40, 135)
    sheet.write()


def uno():
    sheet = Sheet("uno_cc1101", "Arduino Uno R3 + CC1101 fireplace remote (serial only)",
                  ["Bench build. The level shifter is required: the CC1101 is not 5 V tolerant. Not yet built."])
    sheet.place_block(UNO, "U1", "Arduino Uno R3", 50, 70, {
        "1": "+5V", "2": "+3V3", "3": "GND",
        "5": "SCK_5V", "6": "MISO_5V", "7": "MOSI_5V", "8": "CSN_5V",
    })
    sheet.place_block(SHIFTER, "U2", "4-channel BSS138 level shifter", 140, 70, {
        "1": "+5V", "2": "GND", "3": "SCK_5V", "4": "MOSI_5V", "5": "CSN_5V", "6": "MISO_5V",
        "7": "+3V3", "8": "GND", "9": "SCK", "10": "MOSI", "11": "CSN", "12": "MISO",
    })
    sheet.place_block(CC1101, "U3", "CC1101 module, 315 MHz", 230, 70, {
        "1": "+3V3", "2": "GND", "3": "CSN", "4": "SCK", "5": "MOSI", "6": "MISO", "9": "ANT",
    })
    sheet.place_block(ANTENNA, "AE1", "315 MHz antenna", 275, 70, {"1": "ANT"})
    sheet.place_cap("C1", "100nF", 190, 115, "+3V3", "GND")
    sheet.place_cap("C2", "10uF", 215, 115, "+3V3", "GND")
    sheet.note("Never connect a Uno pin straight to the CC1101: 5 V can damage it.", 30, 105)
    sheet.note("Put C1 and C2 at the CC1101 VCC and GND pins.", 30, 110)
    sheet.note("ANT: 315 MHz antenna, or a 23.8 cm wire on modules with a solder pad.", 30, 115)
    sheet.note("GDO0 and GDO2 stay unconnected: this build only transmits.", 30, 120)
    sheet.note("Opening the serial port resets a Uno, and the sketch then forgets the fireplace state.", 30, 125)
    sheet.write()


def write_library():
    blocks = (CC1101, XIAO, UNO, SHIFTER, ANTENNA)
    symbols = [b.symbol() for b in blocks] + [CAP]
    body = "\n".join(symbols).replace('(symbol "proflame:', '(symbol "')
    (OUT / "proflame.kicad_sym").write_text(
        f'(kicad_symbol_lib (version 20241209) (generator "gen_schematics") (generator_version "9.0")\n{body}\n)\n'
    )
    (OUT / "sym-lib-table").write_text(
        '(sym_lib_table\n  (version 7)\n'
        '  (lib (name "proflame")(type "KiCad")(uri "${KIPRJMOD}/proflame.kicad_sym")(options "")(descr ""))\n)\n'
    )


if __name__ == "__main__":
    write_library()
    esp32()
    uno()
