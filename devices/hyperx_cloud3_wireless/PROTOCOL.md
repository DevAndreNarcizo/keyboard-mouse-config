# HyperX Cloud III Wireless — bateria por request/response

Medido em 2026-08-24 na máquina `calecos`, contra o hardware.

## Por que precisou de um diretório

O fone **tem** bateria e **não a declara em canal nenhum que o kernel entenda**:

- o descritor HID não tem Usage Page de bateria (`0x84` Power Device nem `0x85`
  Battery System) — conferido decodificando o descritor, não por grep;
- por consequência ele cai em `hid_generic`, o kernel não cria `power_supply`, e
  não há nada no UPower além do `DisplayDevice`;
- o BlueZ não vê nada: o fone é 2.4G por dongle, não Bluetooth.

Ou seja, os três caminhos automáticos do `kmctl scan` passam batido. O número só
existe atrás de um opcode do fabricante — que é a razão de este repo existir.

## Identificação

| | |
|---|---|
| VID:PID | `03f0:0c9d` (HP) |
| `HID_ID` | `0003:000003F0:00000C9D` |
| interface | Usage Page **`0xff13`**, report **`0x66`** (Output 61 B **e** Input 61 B) |

O `0x0c9d` é o que o app de referência chama de "Cloud III rev 4106" (3229 em
decimal). Há uma segunda revisão, `0x05b7` (1463), que este repo não viu.

**A interface tem que ser achada pela página `0xff13`.** As outras três
interfaces USB do fone são áudio (classe 01) e nem viram `hidraw`.

### O que isso obrigou a mudar no repo

O `find_iface` reconhecia como "página de fabricante" só `0xFF00` e `0xFFFF`. A
faixa vendor-defined da spec HID é **`0xFF00`–`0xFFFF` inteira**, e este fone usa
`0xFF13`: o módulo existia, o aparelho estava plugado, e o `kmctl devices` o
mostrava como ausente — sem erro nenhum. Recortar dois valores da faixa era um
acidente. Corrigido em `devices/_tem_pagina_vendor`.

## O pacote

**Pergunta** — Output report, 52 bytes (o descritor aceita até 61):

```
66 89 00 00 00 ... 00
^^ ^^
|  opcode de status
report ID
```

**Resposta** — Input report no mesmo report `0x66`:

```
66 89 0f 74 4f 00 00 ...
^^ ^^ ^^^^^ ^^
|  |  |     bateria, em % (byte 4)
|  |  tensão da célula em mV, big-endian (bytes 2..3)
|  eco do opcode
report ID
```

Medida real: `66 89 0f 74 4f` → `0x0f74` = **3956 mV**, byte 4 = **79 %**.

### Como se soube que o byte 4 é o percentual sem descarregar o fone

Sozinho, "byte que vale 79" não prova nada. O que fecha é a **tensão ao lado**:
3,956 V é onde uma Li-ion de célula única está com ~79 % de carga. Dois campos
independentes do mesmo frame concordando, e um deles com significado físico
verificável — é o mesmo tipo de evidência que confirmou o M800 PRO (lá, o salto
de recarga).

O app de referência descarta valor `> 100`: é o que o Cloud III S devolve
desligado (`0xff`). O `pct_ok` deste repo já corta isso e o zero.

## Fone desligado: responde, mas zerado

O dongle continua enumerado com o fone desligado, e **responde à pergunta** — com
tudo zerado:

```
66 89 00 00 00     ->  0 mV, 0 %
```

Isso não é leitura ruim: é "não há fone do outro lado". O `pct_ok` já descarta o
zero, mas o `kmctl battery` dizia "não respondeu em 5s", o que manda procurar
defeito onde não há. O módulo implementa o hook opcional `estado()`, que o
`kmctl` usa para dizer **desligado** em vez de "mudo". Medido em 2026-08-25.

## O que não se sabe

- **Flag de carga.** Nenhum byte da resposta mudou de forma reconhecível com o
  cabo ligado. Está em `WONT`, e o `Reading` vai com `charging=None` — que o
  painel desenha sem o `⚡`, em vez de inventar um estado.
- **Os outros reports da página `0xff13`** (`0x06`, `0x07`, `0x0a`, `0x0b`) não
  foram tocados. `0x0b` é Input de 2 B e parece evento, não estado.

## Fonte

Protocolo de [auto94/HyperX-Cloud-2-Battery-Monitor](https://github.com/auto94/HyperX-Cloud-2-Battery-Monitor)
(`Cloud2BatteryMonitorUI/MainForm.cpp` e `MainForm.h`), que declara o PID 3229 e
a interface `usage_page 65299` = `0xFF13`. **Confirmado aqui contra o hardware** —
os bytes acima são os que este fone devolveu, não os que o projeto documenta.

O [HeadsetControl](https://github.com/Sapd/HeadsetControl) **não** serve: o
`hyperx_cloud_3.hpp` dele cobre só o Cloud III **com fio** (`0x089d`, `0x03cc`),
que não tem bateria. O Cloud II Wireless de lá usa outro protocolo
(`06 ff bb <cmd>`, página `0xFF90`) — parecido em espírito, incompatível em bytes.
