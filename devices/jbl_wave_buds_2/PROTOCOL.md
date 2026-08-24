# JBL Wave Buds 2 — não há protocolo aqui

Este arquivo existe para dizer que **não houve engenharia reversa**, e por quê.

O fone reporta bateria pelo próprio Bluetooth (AVRCP/HFP), o BlueZ decodifica e
publica em D-Bus:

```
org.bluez  /org/bluez/hci0/dev_50_1B_6A_0C_F9_73  org.bluez.Battery1  Percentage
```

Conferido contra duas fontes independentes, que concordaram:

```
$ bluetoothctl info 50:1B:6A:0C:F9:73   ->  Battery Percentage: 0x5a (90)
$ upower -i .../headset_dev_50_1B...    ->  percentage: 90%
```

Preferimos o BlueZ ao UPower porque o UPower **cacheia**: no momento do teste ele
dizia `updated: 2669 seconds ago`, ou seja 44 min de atraso. O BlueZ responde o
valor corrente.

## Identificação

`Modalias = bluetooth:v0ECBp2100d001F`. O `IDS` guarda `v0ECBp2100` — vendor e
produto, **sem** o `d001F`, que é release de device e muda com revisão de
firmware. É o análogo exato do `VID:PID` do lado HID.

## O que o BlueZ não dá

- **Nada de carga.** `org.bluez.Battery1` só tem `Percentage`. O fone sabe se
  está no case carregando; não conta. Por isso `Reading.charging` é sempre `None`
  em vez de um palpite.
- **Nada de controle.** Luz, toque, EQ: nada disso aparece em D-Bus. Está tudo em
  `WONT`, para o `kmctl` responder com a frase em vez de uma falha feia.
- **Nada de frame cru.** `Reading.raw` é `b""`, porque o número já vem
  decodificado. Ou seja este modelo não aparece no `kmctl raw` — e não faz
  sentido que apareça, já que não há byte para descobrir.

## Desconectado ≠ ausente

Um fone pareado continua existindo no BlueZ com o `org.bluez.Device1` inteiro,
mas **sem** a interface `Battery1`. Por isso o `find()` exige `Connected == true`
**e** a presença de `Battery1`: sem as duas, o `kmctl` mostraria um aparelho
"plugado" que não tem número nenhum para dar.
