.PHONY: install upgrade uninstall doctor validate

install:
	./install.sh install

upgrade:
	./install.sh upgrade

uninstall:
	./install.sh uninstall

doctor:
	./install.sh doctor

validate:
	python3 -m py_compile $$(find skills/paper-interpretation/scripts -name '*.py' -print)
	python3 scripts/validate_skill_shape.py
