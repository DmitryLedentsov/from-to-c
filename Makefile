PYTHON ?= python3
CC ?= cc

.PHONY: examples test clean

examples:
	$(PYTHON) src/ftc.py examples/counter.ftc -o generated/counter.c
	$(PYTHON) src/ftc.py examples/point.ftc -o generated/point.c


test:
	$(PYTHON) tests/test_examples.py

clean:
	rm -f generated/*.c generated/counter generated/point
