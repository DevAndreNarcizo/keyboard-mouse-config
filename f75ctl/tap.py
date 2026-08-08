#!/usr/bin/env python3
"""Tap nas interfaces HID de entrada do F75: mostra os reports crus das teclas."""
import os, select, sys, time

devs = {}
for n in (7, 8, 9):
    try:
        devs[os.open(f"/dev/hidraw{n}", os.O_RDONLY | os.O_NONBLOCK)] = f"hidraw{n}"
    except OSError as e:
        print(f"hidraw{n}: {e}", flush=True)
end = time.time() + float(sys.argv[1] if len(sys.argv) > 1 else 60)
print(f"tap ativo em {list(devs.values())}", flush=True)
while (left := end - time.time()) > 0:
    for fd in select.select(list(devs), [], [], left)[0]:
        data = os.read(fd, 64)
        if set(data) == {0}:
            continue  # ignora report de "nada pressionado"
        print(f"{devs[fd]}: {data.hex(' ')}", flush=True)
