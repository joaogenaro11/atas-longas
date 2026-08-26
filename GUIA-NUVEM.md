# ☁️ Colocar na nuvem grátis (Hugging Face Spaces)

Objetivo: uma **URL fixa** que você abre de **qualquer lugar** (celular, outro
computador), **sem depender do seu Mac ligado**. Grátis.

> Tradeoffs honestos: a CPU grátis é **mais lenta** (áudio longo demora bem
> mais), o áudio é processado **no servidor da Hugging Face** (não é mais 100%
> local) e o Space **"dorme" após ~2 dias** sem uso (acorda sozinho ao abrir a
> URL, leva ~1 min). Para privacidade, **use senha** (passo 4).

---

## 1. Criar conta (grátis)
Acesse **https://huggingface.co** e crie uma conta (dá pra entrar com o Google).

## 2. Criar o Space
- Clique no seu avatar → **New Space** (ou https://huggingface.co/new-space).
- **Owner:** você. **Space name:** `atas-longas` (ou o nome que quiser).
- **SDK:** escolha **Docker** → template **Blank**.
- **Hardware:** deixe **CPU basic (grátis)**.
- **Visibility:** pode deixar **Public** (com senha no passo 4) ou **Private**.
- Clique **Create Space**.

## 3. Enviar o código pro Space
Pegue um **token** de escrita: Hugging Face → **Settings → Access Tokens →
New token** (tipo *Write*). Copie o token.

No seu Mac, no repositório do projeto:

```bash
cd ~/atas-longas
git fetch origin
git checkout -b nuvem-huggingface origin/nuvem-huggingface   # baixa esta versão de nuvem

# aponta pro seu Space (troque SEU_USUARIO e o nome se mudou)
git remote add space https://huggingface.co/spaces/SEU_USUARIO/atas-longas
git push --force space nuvem-huggingface:main
```

Quando pedir **usuário/senha** do push: usuário é o seu login da Hugging Face e
a **senha é o TOKEN** que você copiou.

O Space vai **construir sozinho** (Docker) — acompanhe a aba **Logs**/“Building”.
Leva alguns minutos na 1ª vez.

## 4. Proteger com senha (recomendado)
No Space: **Settings → Variables and secrets → New secret**:
- **Name:** `APP_PASSWORD`
- **Value:** uma senha sua

Salve e clique em **Restart** (ou **Factory rebuild**). Agora só quem tem a senha
entra (no navegador, usuário pode ser qualquer coisa).

## 5. Usar de qualquer lugar
Abra: **`https://SEU_USUARIO-atas-longas.hf.space`**

Arraste o áudio, entre com a senha, baixe o TXT. Funciona no celular, em outro
computador, em qualquer rede — **sem o seu Mac**.

> 1ª transcrição após o Space acordar é mais lenta (baixa o modelo ~1,6 GB).
> Depois melhora enquanto o Space estiver "acordado".

---

## Atualizar a versão da nuvem depois
Sempre que a gente melhorar esta versão:

```bash
cd ~/atas-longas
git checkout nuvem-huggingface
git pull origin nuvem-huggingface
git push space nuvem-huggingface:main
```

O Space reconstrói sozinho.
