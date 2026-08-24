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
sudo install -m644 layout/victor /usr/share/X11/xkb/symbols/victor

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
if [ -e "$HOME/.XCompose" ] && ! cmp -s layout/XCompose "$HOME/.XCompose"; then
  cp "$HOME/.XCompose" "$HOME/.XCompose.bak-$(date +%Y%m%d%H%M%S)"
  echo "    o que existia foi salvo em ~/.XCompose.bak-*"
fi
install -m644 layout/XCompose "$HOME/.XCompose"

echo "==> regras udev (hidraw sem root)"
sudo install -m644 udev/*.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=hidraw

if command -v gsettings >/dev/null && [ -n "${XDG_CURRENT_DESKTOP:-}" ]; then
  echo "==> input sources do GNOME"
  gsettings set org.gnome.desktop.input-sources sources \
    "[('xkb','victor+quotefix'),('xkb','br')]"
  echo "    victor(quotefix) em primeiro = é o layout padrão, sem Super+Space"

  echo "==> extensão do painel (bateria do teclado/mouse)"
  EXT="$HOME/.local/share/gnome-shell/extensions/battlog@victor"
  mkdir -p "$(dirname "$EXT")"
  ln -sfnT "$PWD/panel/battlog@victor" "$EXT"
  # `gnome-extensions enable` recusa uuid que o shell ainda não varreu (é o caso
  # numa instalação nova), então mexe direto no gsettings — mesma chave.
  python3 - <<'EXTPY'
import ast, subprocess
g = ["gsettings", "get", "org.gnome.shell", "enabled-extensions"]
lst = ast.literal_eval(subprocess.check_output(g, text=True).strip().removeprefix("@as "))
if "battlog@victor" in lst:
    print("    já habilitada")
else:
    lst.append("battlog@victor")
    subprocess.run(g[:1] + ["set"] + g[2:] + [str(lst)], check=True)
    print("    habilitada (aparece depois que o shell reiniciar)")
EXTPY
else
  echo "==> GNOME não detectado, pulando gsettings"
fi

echo "==> serviço de usuário (bateria em tempo real)"
UNIT="$HOME/.config/systemd/user/battlog.service"
mkdir -p "$(dirname "$UNIT")"
sed "s|@REPO@|$PWD|g" systemd/battlog.service > "$UNIT"
systemctl --user daemon-reload
systemctl --user enable --now battlog.service
echo "    battlog.service ativo — `systemctl --user is-active battlog.service`"

# O cron fazia o mesmo trabalho a cada 10 min e ficaria brigando com o serviço
# pelo mesmo arquivo de cache. Sai, e o usuário é avisado do que foi tirado.
if crontab -l 2>/dev/null | grep -q 'kmctl probe'; then
  crontab -l 2>/dev/null | grep -v 'kmctl probe' | crontab -
  echo "    removida a linha de cron do \`kmctl probe\` — o serviço substitui"
fi

cat <<'EOF'

pronto.

O GNOME lê a lista de layouts uma vez, na inicialização, então a variante nova só
aparece depois que o gnome-shell reiniciar:
  - X11: Alt+F2, digite "r", Enter  (não perde janelas)
  - Wayland, ou na dúvida: deslogar e logar

Depois disso o teclado sobe certo em todo login, e sobrevive a plugar/desplugar
teclado — que é o que o arranjo por autostart não fazia.

A bateria no painel é alimentada pelo `battlog.service`, que este script já
habilitou. Ele roda `kmctl watch`: relê a cada 20 s e reage **na hora** a
conectar/desconectar, porque escuta udev e o BlueZ. O painel vigia o arquivo de
cache, então o número aparece no instante em que muda.

  systemctl --user status battlog.service     ver se está de pé
  journalctl --user -u battlog.service -f     acompanhar o que ele lê

Sem o serviço, o painel mostra "—" (de propósito: número velho enganaria).

Prefere cron? `kmctl probe` continua fazendo uma rodada só, e serve:

  */10 * * * * /caminho/para/keyboard-mouse-config/kmctl probe --wait 90 >/tmp/kmctl.log 2>&1

Mas não use os dois: brigariam pelo mesmo arquivo de cache.

`./kmctl devices` mostra o que está aqui com bateria — é a mesma lista que o
painel desenha; `./kmctl selftest` checa o repo sem precisar de hardware.
EOF
