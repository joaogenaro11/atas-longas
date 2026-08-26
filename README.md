# 🎙️ Transcrição de Áudio Local

Ferramenta local para transcrever áudios longos (reuniões de 1–3h) em
português, gerando um **TXT fiel** para depois analisar com IA.

**Tudo roda na sua máquina. Nenhum áudio é enviado para APIs externas. Custo zero.**

```
UPLOAD (web) → FILA → processa em segmentos → junta → TXT
```

Stack: **Python + Flask**, pacotes com **uv**, fila em **SQLite**, empacotável em
**Docker**. Backend de transcrição escolhido automaticamente pelo seu hardware.

---

## Como rodar

### Opção A — Nativo (recomendado, principalmente no Apple Silicon)

```bash
./install.sh     # detecta o hardware, instala uv + dependências + backend
./start.sh       # abre em http://localhost:7860
```

No **Apple Silicon (M1/M2/M3/M4)** isso instala **mlx-whisper** e usa a GPU/Neural
Engine — bem mais rápido. Em **Intel** usa **faster-whisper** (CPU).

### Opção B — Docker (portátil)

```bash
docker compose up --build     # http://localhost:7860
```

> ⚠️ **Docker no macOS não acessa a GPU do Apple Silicon** (roda numa VM Linux).
> Dentro do container só há **faster-whisper (CPU)**, mais lento para áudios de
> várias horas. Para máxima velocidade no Mac, use a **Opção A**.

Requer **FFmpeg** (a Opção A tenta instalar via Homebrew: `brew install ffmpeg`;
na Opção B já vem na imagem).

---

## Como usar

Abra **http://localhost:7860**, arraste os áudios, escolha o modelo e clique em
**Transcrever**. A fila mostra status (aguardando / processando / concluído /
erro), barra de progresso e o link para baixar o `.txt`.

## Onde ficam as coisas

| O quê                     | Onde                              |
|---------------------------|-----------------------------------|
| Áudios enviados           | `data/uploads/`                   |
| Transcrições (`.txt`)     | `transcricoes/` (um por áudio)    |
| Fila / estado dos jobs    | `data/jobs.db` (SQLite)           |
| Cache p/ recuperação      | `transcricoes/.cache/…`           |

`reuniao-cliente.mp3` → `transcricoes/reuniao-cliente.txt`.

## Formatos aceitos

MP3, M4A, WAV, MP4, AAC, FLAC (e OGG/OPUS/WEBM/MOV). O FFmpeg normaliza tudo
para 16 kHz mono antes de transcrever.

## Modelos (preset de qualidade)

| Preset             | Apple Silicon (MLX)          | Intel/CPU/Docker (faster-whisper) |
|--------------------|------------------------------|-----------------------------------|
| Rápido             | whisper-medium               | medium                            |
| **Equilibrado** ⭐ | **whisper-large-v3-turbo**   | large-v3-turbo                    |
| Máxima qualidade   | whisper-large-v3             | large-v3                          |

Com pouca RAM (< 12 GB) cai automaticamente para um modelo mais leve. O modelo é
baixado na primeira execução e fica em cache.

## Áudios longos, batches e recuperação

- Normaliza e **fatia o áudio em segmentos de ~10 min com 15 s de sobreposição**
  (para não perder frases nas divisões).
- **Sequencial (padrão):** mantém contexto entre segmentos → máxima fidelidade.
- **Paralelo (opcional):** campo "Segmentos em paralelo" > 1 processa vários
  batches ao mesmo tempo (mais rápido em CPU multi-core; só no faster-whisper).
- Salva o resultado de **cada segmento** em disco e reescreve o TXT parcial a
  cada etapa. Se cair no meio, o botão **repetir** retoma só o que faltou.

## Formato do TXT

```
Arquivo: reuniao-cliente.mp3
Duração: 01:23:45
Idioma detectado: pt
Modelo: mlx-community/whisper-large-v3-turbo (mlx)
Data da transcrição: 2026-08-18 12:00

============================================================

[00:00:00] texto fiel do que foi dito...

[00:00:47] continuação...
```

Timestamps discretos por bloco (~45 s) para localizar trechos no áudio depois.

## Acessar de qualquer lugar (celular / outro PC)

A transcrição sempre roda **no seu Mac** (é o que dá qualidade máxima de graça).
O que muda é só como você chega até ela de fora.

### Opção recomendada — Tailscale (privado, grátis, sem limite de tamanho)

Cria uma "rede particular" entre o seu Mac e o seu celular. Ninguém mais acessa.

1. No **Mac**: instale (`brew install --cask tailscale`), abra o app e faça login.
2. No **celular**: instale o app **Tailscale** e faça login com a **mesma conta**.
3. No Mac, rode `./start.sh` (deixe rodando).
4. Descubra o endereço do Mac na rede Tailscale (app do Mac mostra algo como
   `100.x.y.z` ou um nome `joaos-macbook`). No celular, abra:
   `http://<endereço-ou-nome>:7860`

Funciona de qualquer rede (4G/5G/Wi-Fi), é privado e aguenta arquivos grandes.

### Opção rápida (turnkey) — link público + QR code

Um comando só. Deixe o Mac ligado com ele rodando:

```bash
./share.sh
```

Ele sobe a aplicação e um túnel da Cloudflare (grátis, sem conta) e mostra:

- o **LINK** `https://…trycloudflare.com` (abra em qualquer lugar),
- um **QR code** — aponte a câmera do celular e abra,
- uma **SENHA** de acesso (usuário pode ser qualquer coisa).

Instala o `cloudflared` sozinho na 1ª vez (via Homebrew). Deixe a janela aberta
enquanto usar; `Ctrl+C` encerra tudo.

> O túnel gratuito limita uploads a **~100 MB por arquivo**. Para áudios de
> várias horas (arquivos grandes), use o **Tailscale** acima (privado, sem limite).

Para fixar sua própria senha: `APP_PASSWORD="minhasenha" ./share.sh`

Para proteger o app com senha em qualquer cenário, rode com:
`APP_PASSWORD="suasenha" ./start.sh`

## Linha de comando (opcional)

```bash
uv run python transcribe.py caminho/audio.m4a transcricoes equilibrado
```

## Não faz (é um MVP proposital)

Sem login, autenticação, nuvem, diarização / identificação de quem falou, resumo
ou análise. Só transcrição fiel → TXT.
