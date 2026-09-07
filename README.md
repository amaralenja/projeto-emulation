# Projeto Emulation

Rodar o app **Minute** (`com.bakerdata.minute`) num emulador Android com a câmera
funcionando, e usar a câmera do emulador como saída para vídeos e para a câmera
do celular ao vivo.

---

## 1. O que já funciona

| | Estado |
|---|---|
| Minute instalado, logado, passando pelo PAIRIP | ✅ |
| Trava de modelo "Galaxy S22 ou superior" | ✅ contornada (`s22spoof`) |
| Trava de câmera ultra-wide na gravação | ✅ contornada (`uwcam`) — a frontal vira simples, ver [docs/uwcam.md](docs/uwcam.md) |
| Vídeo do PC entrando como câmera | ✅ via nativa (`videofile:` + `preparar.py`) |
| Câmera do celular ao vivo entrando como câmera | ❌ dependia do OBS → DroidCam, que não existe mais (§4) |
| Vídeo sobreposto à câmera ao vivo | ❌ mesma causa (§4) |
| **Vídeo/câmera externa dentro da gravação do Minute** | ❌ impossível — ver §6 |

---

## 2. Instalar num PC novo

> **O repositório tem a receita, não o emulador pronto.**
> O AVD tem 8,4 GB e não está aqui. Clonando você *reconstrói* o ambiente:
> os scripts automatizam o download e a configuração, mas três coisas são
> manuais e não têm como automatizar — login na conta Google, instalar o
> Minute pela Play Store e login no Minute. Conte com 1–2 horas, quase tudo
> esperando download.
>
> Se puder levar a pasta do AVD por pendrive, pule para *"Atalho"* abaixo:
> a diferença é 10 minutos contra 2 horas.

Precisa só de **Git** e **PowerShell** (já vem no Windows). Os scripts baixam o resto.

O `01-ferramentas.ps1` instala tudo pelo winget:

| Programa | Para quê |
|---|---|
| JDK 21 + Python 3.12 | rodar o SDK e o `camvideo.py` |
| SDK do Android | emulador, adb, build-tools |
| OBS Studio | compor câmera ao vivo + vídeo |
| **DroidCam Client** | traz o driver de câmera virtual |
| **DroidCam OBS Plugin** | a saída virtual (Ferramentas → DroidCam Virtual Output) |
| ffmpeg | utilitário de vídeo |

### Pré-requisito: aceleração por hardware (precisa de admin)

O emulador x86_64 **não sobe** sem hipervisor. O sintoma é morrer no boot com:

```
ERROR | x86_64 emulation currently requires hardware acceleration!
CPU acceleration status: Android Emulator hypervisor driver is not installed
```

Isso é anterior a tudo neste repositório e os scripts não conseguem resolver:
exige elevação.

**Passo 0 — a virtualização precisa estar ligada no firmware:**

```powershell
(Get-CimInstance Win32_Processor).VirtualizationFirmwareEnabled   # tem que ser True
```

Se der `False`, ligue VT-x (Intel) ou SVM/AMD-V (AMD) no BIOS/UEFI. Sem isso
nenhum dos caminhos abaixo funciona — e essa é a causa mais comum de emulador
travado em PC recém-formatado.

Existem **dois** hipervisores possíveis, e eles são **mutuamente exclusivos**.
Escolher o errado custa caro: o AEHD instala sem reclamar, o driver não carrega,
e você continua com 0% de CPU — agora com um driver a mais no sistema.

#### Preferir WHPX (recurso do Windows)

É o que roda no PC de referência deste projeto, e não envolve driver de
terceiros. Precisa de Windows **Pro/Enterprise**. Num PowerShell **como
administrador**:

```powershell
dism /online /enable-feature /featurename:HypervisorPlatform /all /norestart
```

Reiniciar, e conferir com `emulator -accel-check`.

#### AEHD, só se o WHPX não servir

Cabe quando a edição do Windows é Home, ou quando o WHPX não está disponível.
**Antes**, confirme que nada mais está segurando o hipervisor — se qualquer um
destes estiver ativo, o AEHD não vai carregar:

```powershell
Get-Service vmcompute,vmms -ErrorAction SilentlyContinue   # Hyper-V / WSL2 / Sandbox
Get-CimInstance Win32_DeviceGuard -Namespace root\Microsoft\Windows\DeviceGuard |
    Select-Object -Expand SecurityServicesRunning          # Integridade de memória
(Get-CimInstance Win32_ComputerSystem).HypervisorPresent   # tem que ser False
```

Se estiver tudo limpo, o `01-ferramentas.ps1` já baixou o pacote:

```powershell
cd "$env:LOCALAPPDATA\Android\Sdk\extras\google\Android_Emulator_Hypervisor_Driver"
.\silent_install.bat
```

Em qualquer um dos dois casos, o veredito final é o `emulator -accel-check`.

**Só o Iriun Webcam fica manual** (não está no winget): https://iriun.com/ —
e ele só é necessário para usar a **câmera do celular ao vivo**. Para rodar
vídeo na câmera você não precisa nem dele nem do OBS, o emulador toca o arquivo
sozinho com `-camera-back videofile:...`.

Depois de instalar o OBS, ligue o servidor websocket uma vez em
*Ferramentas → Configurações do WebSocket*. O `camvideo.py` lê a senha sozinho.

```powershell
# a partir da raiz do repositório clonado
cd .\setup
powershell -ExecutionPolicy Bypass -File .\01-ferramentas.ps1
```
Instala JDK, Python, `websockets`, e o SDK do Android (~4,6 GB no disco, demora).

O script confere no fim se os cinco pacotes do SDK chegaram mesmo. Se ele
terminar sem reclamar, o ambiente está de pé; se reclamar, ele diz qual faltou.

**Abra um PowerShell novo** (para o PATH valer) e:

```powershell
powershell -ExecutionPolicy Bypass -File .\02-criar-avd.ps1
```

Depois, **manualmente dentro do emulador**:

1. Abrir a Play Store e fazer login na conta Google
2. Instalar o **Minute Data** pela Play Store
   *(sideload dos APKs em `/apk` **não** passa no PAIRIP — eles são só backup)*
3. Fazer login no Minute

Então, no **Git Bash**:

```bash
bash 03-rootear.sh     # instala o Magisk
# ... seguir as instruções que ele imprime ...
bash 04-modulos.sh     # instala s22spoof e uwcam
```

### Atalho: levar o AVD pronto

O AVD `MinutePlay` tem ~8,4 GB e guarda o login da Play, o Minute instalado e o
root já feito. Copiando ele você pula os passos 02–04:

```
%USERPROFILE%\.android\avd\MinutePlay.avd\     (pasta)
%USERPROFILE%\.android\avd\MinutePlay.ini      (arquivo)
```

O `.ini` tem caminho absoluto dentro — abra e corrija o nome do usuário se mudar.
Ainda precisa rodar o `01-ferramentas.ps1` para ter o SDK.

---

## 3. Estrutura

```
PROJETO EMULATION/
├── README.md              este arquivo
├── setup/                 instalação do zero no PC novo
├── camera/CAMERA.bat      painel: escolhe a fonte da câmera e sobe o emulador
├── camvideo/
│   ├── PAINEL.bat         << ABRE A JANELINHA para trocar o vídeo da câmera
│   ├── painel.pyw         a janelinha em si
│   ├── montar.py          compõe a cena (fundo + sobreposto + texto)
│   ├── preparar.py        só encaixa um vídeo no tamanho da câmera
│   ├── camvideo.py        montava no OBS — via quebrada, ver §4
│   └── videos/            << jogue seus vídeos aqui
├── lentes/                app Android que inspeciona as câmeras (diagnóstico)
├── magisk/                os dois módulos, prontos para instalar
├── docs/                  JSONs originais das câmeras, log de crash
│   └── uwcam.md           como o módulo uwcam é feito, e o que ele custa
└── apk/                   (NÃO vem no clone — está no .gitignore)
```

> `apk/` guardava um backup dos 4 splits do Minute 1.22.0. Fica fora do
> repositório de propósito: é app de terceiros, e sideload não passa no PAIRIP
> de qualquer jeito — a instalação boa é pela Play Store. Se quiser o backup,
> crie a pasta e puxe do próprio emulador depois de instalar:
>
> ```bash
> mkdir -p apk
> adb shell pm path com.bakerdata.minute | sed 's/^package://' \
>   | tr -d '\r' | xargs -I{} adb pull {} apk/
> ```

---

## 4. Como usar

### Trocar o vídeo da câmera — o jeito fácil

Dois cliques em **`camvideo/PAINEL.bat`**. Abre uma janelinha: escolhe o vídeo
da lista (ou de qualquer pasta), opcionalmente escreve um texto por cima, e
clica em **USAR ESTE VÍDEO NA CAMERA**. Duplo clique no nome já aplica.

Ele processa e grava em `%LOCALAPPDATA%\emulation-cam\atual.mp4`, que é o
arquivo que o emulador lê. **Trocar esse arquivo troca o que a câmera mostra.**

O emulador lê o arquivo **no boot** — se ele já estiver aberto, reinicie para a
troca valer.

### Painel do emulador

Abrir **`camera/CAMERA.bat`**:

| Opção | Fonte da traseira | Para quê |
|---|---|---|
| 1 | vídeo (via OBS/DroidCam) | ⚠️ **quebrada** — ver abaixo |
| 2 | Iriun | ⚠️ **quebrada** — ver abaixo |
| 3 | Iriun + vídeo por cima | ⚠️ **quebrada** — ver abaixo |
| 4 | `emulated` | **Minute** (é a única com ultra-wide) |

### Via nativa do emulador — **use esta**

O emulador toca arquivo de vídeo direto como câmera. Dispensa OBS, DroidCam e
ordem de inicialização.

**Passo 1, prepare o vídeo.** Sem isso a imagem chega cortada: o buffer de
câmera do emulador é **1280×720 deitado** e o `sensor.orientation` é 90, então
o app ainda gira o quadro para exibir. Um vídeo vertical 1080×1920 jogado
direto perde ~68% da altura (`1080 ÷ 16/9 = 607` px sobrevivem de 1920).

```bash
cd camvideo
python preparar.py videos/meu.mp4          # gera videos/meu.pronto.mp4
```

Encaixa o vídeo em 1280×720 **sem cortar nada**. Um 16:9 enche o quadro exato;
outros formatos aparecem inteiros, com tarja preta em volta. Não gira — a
orientação fica como estava.

| Opção | Para quê |
|---|---|
| *(padrão)* | cabe inteiro, sem perder nada |
| `--modo cheio` | preenche cortando o excesso |
| `--rot 270` | vídeo vertical em pé numa tela em pé |
| `--espelhar` | espelha na horizontal |

**Precisa compor?** O `montar.py` faz o que o OBS fazia — juntar fundo,
sobreposto e texto — só que o resultado é um arquivo, não um sinal ao vivo:

```bash
python montar.py --fundo videos/base.mp4 --sobre logo.png --texto "AO VIVO" --instalar
python montar.py --cor black --dur 60 --texto "aguarde" --instalar
python montar.py --fundo base.mp4 --sobre pip.mp4 --canto cima-esquerda --escala 0.25 --instalar
```

`--instalar` já copia para `%LOCALAPPDATA%\emulation-cam\atual.mp4`, que é o
caminho sem espaço que o `videofile:` exige. Cantos: `cima-esquerda`,
`cima-direita`, `baixo-esquerda`, `baixo-direita`, `centro`.

**Passo 2, suba com ele:**

```powershell
emulator -avd MinutePlay -no-snapshot -timezone America/Sao_Paulo `
         -camera-back "videofile:C:\caminho\meu.pronto.mp4" -camera-front emulated -gpu auto
```

Também aceita `imagefile:` e `image360:`. Só não serve para o Minute (§6).

> ### ⚠️ O caminho não pode ter espaço
>
> **O `videofile:` do emulador não aceita espaço no caminho, e falha calado.**
> Não é questão de aspas: o emulador sobe normalmente, o `CameraService` abre o
> dispositivo, e simplesmente não chega frame nenhum — o app fica travado
> esperando. Nenhuma mensagem de erro, em lugar nenhum.
>
> Testado com o **mesmo arquivo**, mudando só o caminho:
>
> | Caminho | Resultado |
> |---|---|
> | `C:\PROJETO EMULATION\camvideo\videos\x.mp4` | boot ok, câmera abre, **zero frames** |
> | `C:\Users\...\Temp\x.mp4` | imagem normal |
>
> Isso morde este projeto sempre, porque a pasta se chama **"PROJETO
> EMULATION"**. Copie para um caminho sem espaço antes de usar:
>
> ```powershell
> copy "camvideo\videos\meu.pronto.mp4" "$env:LOCALAPPDATA\Temp\cam.mp4"
> ```
>
> O `camera/CAMERA.bat` já faz isso sozinho (copia para
> `%LOCALAPPDATA%\emulation-cam\atual.mp4`), e o `preparar.py` avisa quando a
> saída cai num caminho com espaço.

### Via OBS — ⚠️ quebrada nas versões atuais

**Não funciona mais**, e não é configuração: a peça que ligava o OBS ao driver
deixou de existir. Verificado com OBS 32.2.1, DroidCam OBS Plugin 2.5.1 e
DroidCam Client 6.5.3:

- O menu **Ferramentas → DroidCam Virtual Output** não existe mais. O
  `droidcam-obs.dll` 2.5.1 não tem nenhuma string "Virtual Output", nem no
  binário nem em `locale/en-US.ini` — ele virou só plugin de *fonte*
  (celular → OBS), com `Activate`, `Deactivate`, `Resolution`, `Device`.
- O DroidCam Client 6.5.3 é só `DroidCamApp.exe`, sem componente de saída.
- A **VirtualCam nativa do OBS não substitui**. O `ffmpeg -list_devices` mostra
  `OBS Virtual Camera` e `DroidCam Source 2` como `@device_sw_` (filtros de
  software), e `DroidCam Source 3` como `@device_pnp_`. O
  `emulator -webcam-list` enumera **só o PnP** — por isso a VirtualCam inicia
  com sucesso e mesmo assim o emulador não a enxerga.

O `camvideo.py` em si continua íntegro: conecta no obs-websocket, autentica,
cria a cena, carrega o vídeo e posiciona — tudo verificado. O que quebrou é o
elo *depois* dele, do OBS para o driver de câmera. Fica no repositório porque
volta a servir se o dev47apps devolver a saída virtual.

Consequência: **câmera do celular ao vivo e vídeo sobreposto não têm caminho
hoje**. Para vídeo, a via nativa acima cobre — e melhor.

```bash
cd camvideo
python camvideo.py --status        # ainda útil para conferir a conexão com o OBS
```

---

## 5. Armadilhas (todas custaram tempo aqui)

**Ordem do DroidCam.** A saída do OBS tem que estar rodando **antes** do emulador
abrir a câmera. Se abrir junto, o driver recusa e a câmera fica preta sem erro
nenhum. Como conferir:

```bash
grep "webcam video active" "$APPDATA/obs-studio/logs/"*.txt | tail -1
```
`video_ok=1` conectou · `video_ok=0` alguém já estava com o dispositivo.

**Locks do AVD.** Se o emulador for morto à força, sobram `*.lock` e o próximo
boot falha com *"Running multiple emulators with the same AVD"*. Apagar:
```
%USERPROFILE%\.android\avd\MinutePlay.avd\*.lock
```

**`-no-snapshot`, não `-no-snapshot-load`.** O emulador estava morrendo com
`exited with code 1` ao salvar o snapshot na saída.

**Iriun é exclusivo.** Se o OBS estiver com ele aberto, o emulador não consegue
usar `webcam1` direto — recebe verde. É um consumidor por vez.

**Iriun em `0x0`.** Se o celular conectar depois que o OBS abriu a fonte, ela fica
sem tamanho. O `camvideo.py --live` desativa e reativa a fonte para reconectar.

**Modelo tem que valer no boot.** `resetprop` com o sistema no ar não adianta,
o Minute já decidiu. Por isso é um módulo Magisk.

**O vídeo chega cortado se não for preparado.** São três reduções empilhadas,
medidas com o `lentes`:

| Etapa | Efeito |
|---|---|
| buffer da câmera | teto de **1280×720**, deitado |
| `sensor.orientation = 90` | o app gira o quadro para exibir |
| exibição em "cheio" | corta para preencher a tela 9:16 |

Um vertical 1080×1920 direto perde ~68% da altura antes de chegar ao app. O
`camvideo/preparar.py` resolve girando e encaixando antes — é o equivalente,
para a via nativa, do que o `recorte_para` do `camvideo.py` fazia dentro do OBS.

**O `uwcam` troca traseira e frontal de lado.** No emulador stock, quem já vem
como multi-camera lógica com físicas é a **frontal** — a traseira é uma câmera
simples. O módulo aproveita o JSON da frontal para montar a traseira, e a
frontal fica com o JSON simples da traseira. Ou seja: **a frontal perde as
câmeras físicas**. Não afeta o Minute (só usa a traseira), mas surpreende quem
for inspecionar a frontal depois. Detalhes e como reverter em
[docs/uwcam.md](docs/uwcam.md).

**`su` via ADB.** Confira primeiro — pode já estar liberado:

```bash
adb shell "su -c id"      # quer ver: uid=0(root)
```

Numa instalação em 2026-09 o root já veio concedido direto do rootAVD, sem
passo manual nenhum. Se **não** responder `uid=0`, aí sim: não basta
*Superuser Access = Apps and ADB* nem *Automatic Response = Grant* — tem que
ligar o botão do **[SharedUID] Shell** na aba Superuser do Magisk.

**Caminhos do Git Bash para o `adb.exe`.** Vale para o `03` **e para o `04`**.
O `pwd` do Git Bash devolve `/c/PROJETO EMULATION`, e o `adb.exe` é binário
Windows: não entende esse formato. No `03` o sintoma é o push falhar calado e o
patch abortar com *"Ramdisk.img uses UNKNOWN compression"*; no `04` é
`adb: error: cannot stat '/c/...': No such file or directory`. Os dois scripts
resolvem com `cygpath -m`, que devolve `C:/PROJETO EMULATION`.

**Caminhos no rootAVD.** `ANDROID_SDK_ROOT` precisa estar no formato `C:/...`.
Com `/c/Users/...` o `adb.exe` não acha o arquivo, o push falha calado e o patch
aborta com *"Ramdisk.img uses UNKNOWN compression"*.

**build-tools 34 quebra com JDK novo.** O `d8` estoura NullPointerException lendo
classe anônima. Use a **37.0.0** (é o que o `01-ferramentas.ps1` instala).

---

## 6. O limite que não dá para vencer

**Não é possível colocar vídeo ou câmera externa dentro da gravação do Minute.**

O emulador usa dois HALs de câmera diferentes:

| Fonte | Tem câmeras físicas? | Mostra conteúdo seu? |
|---|---|---|
| `emulated` | ✅ **sim** — lê nosso JSON | ❌ só a cena 3D sintética |
| `virtualscene` | ❌ não | 🟡 só um pôster estático na parede |
| `webcam0` / `videofile:` | ❌ não (HAL legacy) | ✅ sim |

**Só o `emulated` tem as físicas** — nem mesmo o `virtualscene`, que também é
sintético. Testado: com `-camera-back virtualscene` o `lentes` reporta *"sem
cameras fisicas: nao e multi-camera logica"*, e o `dumpsys media.camera` não
mostra `physicalIds`. Isso mata a ideia de usar `-virtualscene-poster` para
enfiar uma imagem sua numa fonte que o Minute aceite: o pôster carrega, mas as
físicas somem junto.

O Minute exige uma **ultra-wide física** e grava a partir dela:

```
EgoCameraCtrl: resolveUltraWide: logical=0 ultraWide=4
```

Sem ela, a gravação é recusada — o log é explícito, e a mensagem na tela
(*"Recording isn't available"*) só aparece ao apertar gravar, porque a
**prévia funciona normalmente** em qualquer fonte:

```
resolveUltraWide: candidate id=0 fov=43.6 focals=[5.0] physicals=[]
resolveUltraWide: ultraWide=null
[useEgoRecorder] start error: 'No ultra-wide physical camera available'
                             | reason: 'no-ultrawide'
```

Isso engana: dá para montar tudo, ver a imagem na prévia e só descobrir o
problema no momento de gravar.

A única fonte com físicas é a que não aceita conteúdo externo. Não há
interseção.

É arquitetura do emulador, não configuração. Na prática:

- **Minute** → traseira `emulated`
- **Prank / live** (TikTok, Instagram, WhatsApp) → `videofile:` ou webcam

---

## 7. Bug para reportar ao dev do Minute

`EgoCameraController.resolveUltraWide` lê `CameraCharacteristics.CONTROL_ZOOM_RATIO_RANGE`
sem checar a versão do Android. Em Android 9/10 isso derruba o app com
`NoSuchFieldError` ao abrir a câmera (log em `docs/minute-crash-camera-android9.txt`).

```kotlin
if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
    // só aqui ler CONTROL_ZOOM_RATIO_RANGE
}
```

E a mensagem *"A câmera deste telefone não está na lista de dispositivos
suportados"* sugere uma allowlist de modelos, quando na verdade é checagem de
capacidade de hardware. Isso levou a horas de investigação na direção errada.

---

## 8. Referência rápida

```
AVD ................ MinutePlay (Android 13, API 33, google_apis_playstore, x86_64)
Modelo forjado ..... SM-S901B (Galaxy S22)
Ultra-wide forjada . física 4, FOV 119,4° (focal 1,7 mm / sensor 4,66×3,50 mm)
Webcams ............ webcam0 = DroidCam (OBS) · webcam1 = Iriun (celular)
Teto de resolução .. 1280×720 quando a fonte é webcam (limite do emulador)
Minute ............. 1.22.0 (versionCode 1004023), React Native + Expo, PAIRIP
```
