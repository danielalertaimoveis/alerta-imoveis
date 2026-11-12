# Alerta de apartamentos para alugar

Este programa confere os sites de imóveis de Londrina várias vezes por hora e avisa,
por Telegram e por e-mail, quando aparece um apartamento dentro do perfil definido em
`config.json`: até 15 minutos a pé do ponto de referência, 2 quartos ou mais, com garagem
e até R$ 3.000 somando aluguel, condomínio e IPTU.

Ele roda sozinho nos servidores do GitHub, de graça, com o seu computador desligado.

## O que ele consulta

| Fonte | O que traz |
|---|---|
| Chaves na Mão | Anúncios de dezenas de imobiliárias de Londrina, com a localização no mapa |
| Imobiliária Inglaterra, Europa e Londrina Norte | Direto do site de cada uma |
| CRV Imobiliária, Human Imóveis e Sérgio Cortez | Direto do site de cada uma |
| Imobiliária Perez | Direto do site, só os apartamentos do Centro |
| Century 21 Class | Direto do site: os 30 primeiros do Centro e os 30 primeiros da cidade |
| Imobiliária Santamérica | Direto do site, os mais novos. Sem rua: o alerta sai com "distância não calculada" |
| Alugaflex | Direto do site, todos os apartamentos de Londrina |
| Imobiliária Veneza | Direto do site, apartamentos de 2 e 3 quartos do Centro |
| Imobiliária Atual | Direto do site, apartamentos de 2 e 3 quartos do Centro. Sem rua |
| Catuaí Imóveis | Direto do site, apartamentos do Centro, lida a cada 30 minutos |
| Raul Fulgêncio e Serenity | Direto do site, mas só os 12 imóveis do topo da lista de cada uma |
| Imob3M, Camponesa, Barreto e Monaco | Direto do site de cada uma, os mais recentes primeiro |
| 88 Imóveis e Imobiliária Natal | Direto do site, todos os apartamentos com localização |
| CMSouza e Imobiliária Senador | Direto do site: os 30 primeiros do Centro e os 30 primeiros da cidade |

A Imobiliária Avenida ficou de fora: o site mostra só os 12 aluguéis mais caros.

Alugaflex e Serenity estão desligadas (`"ativa": false` no `config.json`): os dois sites
funcionam a partir de um computador no Brasil, mas recusam o acesso vindo dos servidores do
GitHub. Os anúncios delas que também vão para o Chaves na Mão continuam chegando por lá.
Para religar uma fonte, apague o `"ativa": false` da linha dela.

Viva Real, ZAP, OLX e Imovelweb bloqueiam programas e ficaram de fora. No ZAP e no Viva Real
dá para criar um alerta próprio do site (botão "Criar alerta" na página de uma busca), que
manda e-mail quando entra anúncio novo.

## Como ler um alerta

- **Minutos a pé**: calculados pela rua, não em linha reta.
- **Localização aproximada**: o anúncio não mostra o número do prédio. Confira o endereço antes de se animar.
- **Condomínio não informado**: o total pode passar do limite.
- **Elevador: não informado**: o anúncio não fala em elevador. Não quer dizer que não tem.
- **Mesmo endereço e valor de um anúncio de...**: provavelmente é o mesmo apartamento em outra imobiliária.

No primeiro dia você recebe uma lista com tudo o que já está anunciado. Depois, só o que for novo
ou mudar de preço. Uma vez por dia, de manhã, chega uma mensagem curta dizendo que o monitor
continua funcionando.

---

## Instalação (uma vez só, uns 20 minutos)

### 1. Criar o bot do Telegram

1. No Telegram, procure por **@BotFather** e abra a conversa.
2. Envie `/newbot`. Ele pede um nome (ex.: `Alerta Imóveis`) e um nome de usuário terminado em `bot`
   (ex.: `alerta_imoveis_daniel_bot`).
3. Ele responde com um **token**, parecido com `123456789:AAH...`. Guarde.
4. Abra a conversa com o bot que você acabou de criar e envie qualquer mensagem (ex.: `oi`).
5. No navegador, abra `https://api.telegram.org/botSEU_TOKEN/getUpdates`, trocando `SEU_TOKEN` pelo token.
   Procure o trecho `"chat":{"id":123456789` — esse número é o seu **chat id**. Guarde.

Para sua esposa receber também: crie um grupo no Telegram com vocês dois e o bot, envie uma mensagem
no grupo e repita o passo 5. O chat id de grupo começa com um sinal de menos.

### 2. Criar a senha de aplicativo do Gmail

O programa envia os e-mails pela sua própria conta do Gmail, usando uma senha separada
que só serve para isso.

1. Em <https://myaccount.google.com/security>, ative a **Verificação em duas etapas** (se ainda não estiver ativa).
2. Abra <https://myaccount.google.com/apppasswords>, dê um nome (ex.: `alerta imoveis`) e clique em **Criar**.
3. O Google mostra uma senha de 16 letras. Guarde.

### 3. Criar a conta e o repositório no GitHub

1. Crie uma conta gratuita em <https://github.com/signup>.
2. Clique em **+** (canto superior direito) → **New repository**.
3. Nome: `alerta-imoveis`. Escolha **Public**. Não marque mais nada. Clique em **Create repository**.

**Por que público:** repositório público roda de graça sem limite. Em repositório privado o GitHub dá
2.000 minutos por mês, e a verificação a cada 10 minutos gasta mais do que isso. O que fica visível é
o código e o `config.json` (critérios e a coordenada do ponto de referência). Token, senha e e-mail
ficam nos *Secrets* e não aparecem para ninguém. Se preferir privado, troque `*/10` por `*/20` em
`.github/workflows/monitor.yml`.

### 4. Enviar os arquivos

Peça ao Claude para enviar os arquivos, informando o endereço do repositório
(ex.: `https://github.com/seu-usuario/alerta-imoveis`). Vai abrir uma janela do GitHub pedindo
o seu login.

### 5. Guardar as senhas no GitHub

No repositório: **Settings** → **Secrets and variables** → **Actions** → **New repository secret**.
Crie estes cinco, um de cada vez:

| Nome | Valor |
|---|---|
| `TELEGRAM_BOT_TOKEN` | o token do passo 1 |
| `TELEGRAM_CHAT_ID` | o chat id do passo 1 |
| `EMAIL_USUARIO` | seu endereço do Gmail |
| `EMAIL_SENHA_APP` | a senha de 16 letras do passo 2 |
| `EMAIL_DESTINO` | para onde mandar os alertas (pode ser o mesmo endereço; para mais de um, separe com vírgula) |

### 6. Testar e ligar

1. Abra a aba **Actions** do repositório. Se aparecer um botão pedindo para habilitar, clique.
2. Clique em **Monitor de imóveis** → **Run workflow**, marque **Enviar só uma mensagem de teste** e confirme.
   Em um minuto deve chegar uma mensagem no Telegram e um e-mail.
3. Clique em **Run workflow** de novo, agora sem marcar nada. Essa primeira verificação leva uns
   3 minutos e manda a lista inicial.

A partir daí ele roda sozinho: a cada 10 minutos das 7h às 21h e uma vez por hora de madrugada.
O GitHub às vezes atrasa alguns minutos em horário de pico.

---

## Ajustes

Tudo fica em `config.json`:

- `minutos_a_pe_max`, `quartos_min`, `valor_total_max`, `exigir_garagem`: os critérios.
- `raio_busca_m`: raio da busca em linha reta. Aumente junto se aumentar os minutos.
- `bairros_proximos`: usados só quando o anúncio não traz rua nem coordenada.
- `bairros_distantes`: bairros longe que às vezes aparecem com a localização errada no mapa.
- `fontes`: para tirar um site, apague a linha dele.

Para pausar: aba **Actions** → **Monitor de imóveis** → **⋯** → **Disable workflow**.

## Testar no seu computador

```
python monitor.py --sem-enviar
```

Mostra na tela o que seria enviado, sem enviar nem gravar nada.

## Se algo parar

- Se uma fonte falhar 12 vezes seguidas, chega um aviso no Telegram com o erro.
- Se a mensagem diária parar de chegar, abra a aba **Actions** e veja a última execução.
- Os sites mudam de formato de vez em quando. Quando isso acontecer, o leitor daquele site
  (em `alerta/fontes/`) precisa de ajuste.
