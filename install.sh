#!/usr/bin/env bash
# Instala esta configuração de teclado numa máquina. Rodar SEM sudo — ele pede
# sozinho para as partes que precisam.
#
# Idempotente: pode rodar de novo à vontade. E precisa mesmo, num caso —
# um `apt upgrade` do pacote xkb-data reescreve o evdev.xml e apaga a entrada da
# variante. Quando o ª/º parar de funcionar logo depois de um upgrade, é isto.
set -euo pipefail
cd "$(dirname "$(realpath "$0")")"

XML=/usr/share/X11/xkb/rules/evdev.xml

echo "==> variante XKB victor(quotefix)"
sudo install -m644 xkb/victor /usr/share/X11/xkb/symbols/victor

if grep -q "<name>victor</name>" "$XML"; then
  echo "    evdev.xml: entrada já existe"
else
  sudo cp --update=none "$XML" "$XML.orig-victor" || true
  sudo python3 - "$XML" <<'PY'
import sys
path = sys.argv[1]
block = """    <layout>
      <configItem>
        <name>victor</name>
        <shortDescription>vic</shortDescription>
        <description>Victor (US intl + ABNT2)</description>
        <languageList><iso639Id>por</iso639Id></languageList>
      </configItem>
      <variantList>
        <variant>
          <configItem>
            <name>quotefix</name>
            <description>Victor (US intl + ABNT2, aspas/ordinais)</description>
          </configItem>
        </variant>
      </variantList>
    </layout>
"""
xml = open(path).read()
assert "  </layoutList>" in xml, "layoutList nao encontrado - evdev.xml mudou de formato"
open(path, "w").write(xml.replace("  </layoutList>", block + "  </layoutList>", 1))
PY
  # ponytail: contagem de tags no lugar de um parser XML — o bloco inserido é
  # literal fixo, o único erro possível é ele não fechar. evdev.xml quebrado
  # deixaria o sistema sem nenhum layout, daí a checagem existir.
  if [ "$(grep -c '<layout>' "$XML")" != "$(grep -c '</layout>' "$XML")" ]; then
    echo "    evdev.xml desbalanceado — restaurando"; sudo cp "$XML.orig-victor" "$XML"; exit 1
  fi
  echo "    evdev.xml: entrada adicionada (backup em $XML.orig-victor)"
fi

echo "==> Compose (~/.XCompose)"
if [ -e "$HOME/.XCompose" ] && ! cmp -s xkb/XCompose "$HOME/.XCompose"; then
  cp "$HOME/.XCompose" "$HOME/.XCompose.bak-$(date +%Y%m%d%H%M%S)"
  echo "    o que existia foi salvo em ~/.XCompose.bak-*"
fi
install -m644 xkb/XCompose "$HOME/.XCompose"

echo "==> regras udev (hidraw sem root)"
sudo install -m644 udev/*.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=hidraw

if command -v gsettings >/dev/null && [ -n "${XDG_CURRENT_DESKTOP:-}" ]; then
  echo "==> input sources do GNOME"
  gsettings set org.gnome.desktop.input-sources sources \
    "[('xkb','victor+quotefix'),('xkb','br')]"
  echo "    victor(quotefix) em primeiro = é o layout padrão, sem Super+Space"
else
  echo "==> GNOME não detectado, pulando gsettings"
fi

cat <<'EOF'

pronto.

O GNOME lê a lista de layouts uma vez, na inicialização, então a variante nova só
aparece depois que o gnome-shell reiniciar:
  - X11: Alt+F2, digite "r", Enter  (não perde janelas)
  - Wayland, ou na dúvida: deslogar e logar

Depois disso o teclado sobe certo em todo login, e sobrevive a plugar/desplugar
teclado — que é o que o arranjo por autostart não fazia.

Se esta máquina tem o teclado/mouse e você quer o log de bateria, adicione ao
`crontab -e` (ajuste o caminho):

  */10 * * * * /caminho/para/keyboard-config/battlog/battlog.py probe --wait 90 >/tmp/battlog.log 2>&1
EOF
