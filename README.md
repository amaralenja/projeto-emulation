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
| Vídeo do PC entrando como câmera | ✅ duas vias (nativa e OBS) |
| Câmera do celular ao vivo entrando como câmera | ✅ via Iriun + OBS |
| Vídeo sobreposto à câmera ao vivo | ✅ via OBS |
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
│   ├── camvideo.py        monta a imagem no OBS (câmera ao vivo + vídeo)
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

### Painel

Abrir **`camera/CAMERA.bat`**:

| Opção | Fonte da traseira | Para quê |
|---|---|---|
| 1 | vídeo (via OBS/DroidCam) | prank com vídeo |
| 2 | Iriun | sua câmera ao vivo |
| 3 | Iriun + vídeo por cima | live com sobreposição |
| 4 | `emulated` | **Minute** (é a única com ultra-wide) |

### Via nativa do emulador (mais simples, sem OBS)

Descoberta tardia: o emulador toca arquivo de vídeo direto como câmera.

```powershell
emulator -avd MinutePlay -no-snapshot -timezone America/Sao_Paulo `
         -camera-back "videofile:C:\caminho\para\seu\video.mp4" -camera-front emulated -gpu auto
```

Também aceita `imagefile:` e `image360:`. **Prefira isso** para vídeo simples:
dispensa OBS, DroidCam, ordem de inicialização e redimensionamento duplo.
Só não serve para o Minute (§6).

### Via OBS (necessária só para câmera ao vivo, ou vídeo + câmera juntos)

```bash
cd camvideo    # a partir da raiz do repositório clonado

python camvideo.py videos/meu.mp4              # só o vídeo, tela cheia
python camvideo.py --live                      # só a câmera do celular
python camvideo.py videos/meu.mp4 --live       # câmera + vídeo no canto
python camvideo.py videos/meu.mp4 --live --sobre cheio
python camvideo.py --live --cam-deitada        # câmera 16:9 inteira (apps deitados)
python camvideo.py --listar-cams
python camvideo.py --status
```

Precisa de OBS com **obs-websocket** ligado e o plugin **DroidCam Virtual Output**.

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

**O `uwcam` troca traseira e frontal de lado.** No emulador stock, quem já vem
como multi-camera lógica com físicas é a **frontal** — a traseira é uma câmera
simples. O módulo aproveita o JSON da frontal para montar a traseira, e a
frontal fica com o JSON simples da traseira. Ou seja: **a frontal perde as
câmeras físicas**. Não afeta o Minute (só usa a traseira), mas surpreende quem
for inspecionar a frontal depois. Detalhes e como reverter em
[docs/uwcam.md](docs/uwcam.md).

**`su` via ADB.** Não basta *Superuser Access = Apps and ADB* nem
*Automatic Response = Grant*. Tem que ligar o botão do **[SharedUID] Shell** na
aba Superuser do Magisk.

**Caminhos no rootAVD.** `ANDROID_SDK_ROOT` precisa estar no formato `C:/...`.
Com `/c/Users/...` o `adb.exe` não acha o arquivo, o push falha calado e o patch
aborta com *"Ramdisk.img uses UNKNOWN compression"*.

**build-tools 34 quebra com JDK novo.** O `d8` estoura NullPointerException lendo
classe anônima. Use a **37.0.0** (é o que o `01-ferramentas.ps1` instala).

---

## 6. O limite que não dá para vencer

**Não é possível colocar vídeo ou câmera externa dentro da gravação do Minute.**

O emulador usa dois HALs de câmera diferentes:

| Fonte | HAL | Tem câmeras físicas? |
|---|---|---|
| `emulated` / `virtualscene` | `device@1.1/internal` | ✅ sim — lê nosso JSON |
| `webcam0` / `videofile:` | `device@3.3/legacy` | ❌ não |

O Minute exige uma **ultra-wide física** e grava a partir dela:

```
EgoCameraCtrl: resolveUltraWide: logical=0 ultraWide=4
```

Câmeras físicas só existem no HAL sintético, e o HAL sintético não aceita
conteúdo externo. Qualquer fonte com imagem real cai no HAL legacy, que não tem
onde declarar físicas — daí o `physicals=[]` e o
*"No ultra-wide physical camera available"*.

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
