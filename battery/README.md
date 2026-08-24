# battery — histórico de bateria

SQLite, stdlib, sem daemon. Este módulo não conhece modelo nenhum: pergunta ao
[`devices/`](../devices/README.md) quem está plugado e guarda o que cada um
devolver.

```bash
./kmctl probe        # grava uma rodada (é o que o cron roda)
./kmctl raw          # quais bytes variaram e como (achar bateria em modelo novo)
./kmctl show         # timeline
./kmctl status       # último valor de cada categoria, e atualiza o cache do painel
```

Regra udev (hidraw sem root) — o `install.sh` já faz:

```bash
sudo install -m644 udev/*.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger --subsystem-match=hidraw
```

Cron, a cada 10 min:

```
*/10 * * * * /caminho/para/keyboard-mouse-config/kmctl probe --wait 90 >/tmp/kmctl.log 2>&1
```

O `--wait` é o tempo esperando um **mouse** se anunciar: os receptores só falam
com o mouse em uso, então metade das rodadas não tem mouse — e isso é normal,
não defeito.

## Widget no painel do GNOME

`../panel/battlog@victor/` — extensão de dois arquivos que mostra os dois
percentuais na barra de cima, ao lado do Astra Monitor.

Ela **não fala com hardware**: o `probe` reescreve `~/.cache/battlog-status`
(troca atômica) no fim de cada rodada, e a extensão relê esse arquivo a cada
2 min. Uma linha por categoria, com o modelo escolhido no meio:

```
ts 1787495551
keyboard attackshark_k86 100
mouse delux_m900pro 66
```

Três decisões que valem o comentário:

- **O valor vem da última linha do banco, não da rodada atual.** Mouse parado
  não gastou bateria: repetir o último número é mais verdadeiro que apagá-lo.
- **`ts` mais velho que 30 min vira `—`.** É o cron que morreu, e um número
  velho no painel engana justamente por parecer atual.
- **Quem descobre os aparelhos é o Python, não a extensão.** O cache traz uma
  linha por aparelho presente e a extensão desenha o que vier; ela não escolhe
  nada. `kmctl devices` mostra a mesma lista.

  Houve um mecanismo de desempate aqui — um aparelho por categoria, com
  `~/.config/keyboard-mouse.conf` decidindo empate e, sem config, vencendo quem
  reportou por último. **Foi removido em 2026-08-24 junto com o `pick()` e o
  `recency()`.** Ele existia porque o painel só cabia um de cada; mostrando
  todos, não há empate a desfazer. Configuração que não decide mais nada é pior
  que nenhuma, porque continua parecendo que decide.

O Astra Monitor não serve de casa para isso: a versão 42 não tem sensor por
comando (o `sensors-source` dele só lê `hwmon`), então seria preciso um driver
de kernel falso só para expor dois inteiros.

## Dados

`battlog.db`, ao lado deste arquivo e fora do git: `raw(ts, device, hex)` com os
bytes crus e `battery(ts, device, pct, charging)` com o que os parsers extraíram.
`device` é o id do módulo (`attackshark_k86`), o que mantém hardwares diferentes
separados na mesma timeline.

Guardar o frame **inteiro** no `raw` é o que permite corrigir um parser sem ter
perdido histórico — já aconteceu duas vezes. É também o que alimenta o
`kmctl raw`, o caminho para achar o byte de bateria de um modelo novo.

Poda de **90 dias** roda dentro do próprio `probe` (`--keep` muda o prazo); não
há segunda rotina para agendar.
