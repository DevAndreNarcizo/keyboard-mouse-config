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

## É o fone, não a caixinha

Primeira pergunta que se faz sobre bateria de TWS, e a estrutura responde sem
precisar de experimento:

- O `Battery1` pendura no objeto **do device Bluetooth**
  (`dev_50_1B_6A_0C_F9_73`), que é o endpoint de rádio, ou seja os fones.
- **A caixinha não tem endereço Bluetooth.** Medido: o BlueZ conhece exatamente
  um aparelho nesta máquina, e é o par de fones. A caixinha não aparece em nenhum
  objeto D-Bus. O cabo alimenta ela, mas quem reporta bateria é quem tem rádio.
- Existe **uma única** interface `Battery1` — não há entrada separada para
  esquerdo, direito ou case.

Confirmação empírica, se quiser: com os fones em uso o número tem que **cair**.
Se estivesse lendo a caixinha no carregador, subiria.

## O que não se sabe: qual dos dois fones

O BlueZ expõe **um** percentual, e o `Battery1` desta versão (BlueZ 5.72) só tem
`Percentage` — a propriedade `Source`, que diria se o número veio de HFP, AVRCP
ou GATT, não existe aqui. Então não há como saber se 90% é o fone esquerdo, o
direito, ou o menor dos dois.

Não tem conserto do nosso lado: quem agrega os dois num número é o firmware do
fone, antes de mandar. Fica registrado para ninguém tentar "melhorar" isso.

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
