# Quando o mouse Attack Shark chegar

Preparado em 2026-08-24, **sem o hardware na mão**. Nada aqui foi testado contra
um Attack Shark: é terreno preparado para o momento em que você plugar, não
suporte pronto.

## O que já está pronto

- **Permissão de hidraw.** Os IDs conhecidos de mouse da marca já estão em
  `udev/99-attackshark.rules`, então você não vai precisar de sudo depois:

  | modelo | IDs | fonte |
  |---|---|---|
  | R5 Ultra | `373e:0046`, `373e:0047` | [maxboeer/attackshark-battery-bridge](https://github.com/maxboeer/attackshark-battery-bridge) |
  | X11 (e talvez R1) | `1d57:fa60`, `1d57:fa55`, `1d57:fa61` | [HarukaYamamoto0/attack-shark-x11-driver](https://github.com/HarukaYamamoto0/attack-shark-x11-driver) |

  Isso era necessário porque a regra de VID `1d57` que já existia prende o PID
  `fa65`, que é o receptor do Delux, e não cobriria um Attack Shark do mesmo VID.

- **`kmctl scan`** responde em segundos se o aparelho já funciona.
- **`kmctl dump`** despeja tudo o que a engenharia reversa precisa, num comando.

## O que NÃO está pronto

**Não existe módulo de mouse Attack Shark.** A marca está no repo só como
teclado (`attackshark_k86`). Se o seu mouse não cair num dos caminhos
automáticos, ele **não vai aparecer** até alguém mapear o protocolo dele.

## O procedimento, quando plugar

```bash
cd keyboard-mouse-config
./kmctl scan          # 1. já funciona?
```

**Se disser `APARECE`** — pronto, acabou. Confirme com `./kmctl battery` e o
painel pega em segundos.

**Se disser que não aparece**, colete o diagnóstico:

```bash
./kmctl dump --seconds 30 > /tmp/attackshark.txt
#  ^ USE o mouse durante os 30 s: mexa, clique, role a roda.
#    Silêncio de aparelho parado não é a mesma coisa que canal mudo, e sem
#    a testemunha do canal de movimento não se distingue uma coisa da outra.
```

O arquivo tem tudo: VID:PID, strings USB, protocolo de cada interface,
descritores, permissões, o resultado da sonda da família conhecida, e a captura
dos canais. É o que eu levantei à mão para o M800 PRO em dezenas de comandos.

## Como ler o resultado

| o que o dump mostra | significa |
|---|---|
| `power_supply` numa interface | o kernel já expõe a bateria — funciona sozinho |
| `bateria_hid` | declara a página padrão de bateria; devia gerar `power_supply` |
| sonda devolveu `('XXXX', 42)` | é da família Delux/TeLink — **funciona sozinho** |
| `familia_0x0c` mas a sonda não respondeu | declara o report mas fala outro protocolo |
| frames com `<- parece ...` na escuta | a família de anúncio foi reconhecida |
| `vendor` e mais nada | canal de fabricante desconhecido: precisa de engenharia reversa |

## Uma hipótese que vale testar primeiro

**O X11 usa o VID `1d57` — o mesmo do receptor Delux M900Pro** que passou por
esta máquina (`1d57:fa65`, strings "Xenta/LXDDZ 2.4G 8K HS Receiver"). Os dois
saem do mesmo OEM, então é plausível que compartilhem o protocolo — que no
M900Pro é de **anúncio**: report `0x03`, frame de 5 bytes, bateria no byte 4.

Se for isso, o `dump` vai mostrar na escuta frames marcados
`<- parece Delux M900Pro`, e o módulo sai quase de graça: copiar
`devices/delux_m900pro/` e trocar o `IDS`. **Cuidado:** o byte de bateria daquele
módulo é marcado como *provisório* no `PROTOCOL.md` dele, então herdaria a mesma
ressalva.

## Atalho, se o seu for um R5 Ultra

O [attackshark-battery-bridge](https://github.com/maxboeer/attackshark-battery-bridge)
publica a bateria do R5 Ultra em `power_supply`. **Se você rodar aquele daemon, o
`power_supply_any` deste repo pega o mouse sem uma linha de código nova aqui.**
É a arquitetura de fontes genéricas se pagando — vale tentar antes de mapear
protocolo nenhum.

O driver do X11, por outro lado, lista bateria como *planejada, não
implementada*, então dele não sai atalho.

## Duas ressalvas honestas

- **O `dump` não escuta interface que declara teclado.** Nesses receptores a
  interface do canal de fabricante costuma ser *também* a de teclado — foi o caso
  do M800 PRO —, e ler o stream dela é gravar o que você digita. A interface
  aparece no relatório com flags e descritor; o `read()` não acontece. Se o
  protocolo do seu mouse for de anúncio **nessa** interface, o dump não vai pegar,
  e aí o caminho é um teste dirigido, com consentimento explícito e o teclado sem
  uso.
- **A sonda só manda a consulta de status da família que o repo conhece**, e só
  onde o descritor declara aquele report. Ela não fuzzeia opcode: mandar byte
  desconhecido para o canal de config de um mouse pode desconfigurá-lo.
