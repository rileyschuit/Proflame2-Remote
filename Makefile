LIB := libraries/Proflame2/src
CXXFLAGS := -std=c++17 -Wall -Wextra -Werror -I$(LIB)
FRAME := $(LIB)/Proflame2Frame.cpp
RTL_433 ?= rtl_433
FQBN_UNO := arduino:avr:uno
FQBN_XIAO := esp32:esp32:XIAO_ESP32S3
FQBN_DEVKIT := esp32:esp32:esp32s3
ARDUINO := arduino-cli compile --warnings default --libraries libraries

.PHONY: test roundtrip compile pi-test schematics clean

test:
	mkdir -p tests/bin
	$(CXX) $(CXXFLAGS) tests/test_host.cpp $(FRAME) $(LIB)/Proflame2Controller.cpp -o tests/bin/test_host
	tests/bin/test_host

roundtrip:
	mkdir -p tests/bin
	$(CXX) $(CXXFLAGS) tests/gen_ook.cpp $(FRAME) -o tests/bin/gen_ook
	python3 tests/rtl433_roundtrip.py tests/bin/gen_ook $(RTL_433)

compile:
	$(ARDUINO) --fqbn $(FQBN_UNO) arduino_serial_input
	$(ARDUINO) --fqbn $(FQBN_XIAO) arduino_serial_input
	$(ARDUINO) --fqbn $(FQBN_XIAO) esp32s3_mqtt_rest
	$(ARDUINO) --fqbn $(FQBN_DEVKIT) esp32s3_mqtt_rest

# Needs python3 with pi/ installed (pip install -e 'pi[test]') and mosquitto on the PATH.
pi-test:
	mkdir -p tests/bin
	$(CXX) $(CXXFLAGS) tests/gen_burst.cpp $(FRAME) -o tests/bin/gen_burst
	cd pi && GEN_BURST=$(CURDIR)/tests/bin/gen_burst python3 -m pytest -q

# Needs kicad-cli 9.
schematics:
	python3 hardware/gen_schematics.py
	for s in esp32s3_cc1101 uno_cc1101 rpi_cc1101; do \
	  kicad-cli sch erc --exit-code-violations -o /tmp/$$s.rpt hardware/$$s.kicad_sch || { cat /tmp/$$s.rpt; exit 1; }; \
	  kicad-cli sch export pdf -o hardware/$$s.pdf hardware/$$s.kicad_sch; \
	  kicad-cli sch export svg --no-background-color --exclude-drawing-sheet -o hardware hardware/$$s.kicad_sch; \
	  python3 hardware/svg_white_background.py hardware/$$s.svg; \
	done

clean:
	rm -rf tests/bin
