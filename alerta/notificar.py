"""Envio dos alertas por Telegram e por e-mail, e montagem dos textos."""
import html
import json
import os
import re
import smtplib
import urllib.parse
import urllib.request
from email.message import EmailMessage


def canais():
    return {
        "telegram": bool(os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID")),
        "email": bool(os.environ.get("EMAIL_USUARIO") and os.environ.get("EMAIL_SENHA_APP")),
    }


def _telegram(metodo, campos):
    url = f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}/{metodo}"
    campos = dict(campos, chat_id=os.environ["TELEGRAM_CHAT_ID"], parse_mode="HTML")
    req = urllib.request.Request(url, data=urllib.parse.urlencode(campos).encode())
    with urllib.request.urlopen(req, timeout=30) as r:
        if not json.load(r).get("ok"):
            raise RuntimeError("Telegram recusou a mensagem")


def enviar_telegram(texto, foto=None):
    """Manda com foto quando possível; se a foto falhar, manda só o texto."""
    visivel = re.sub(r"<[^>]+>", "", texto)  # o limite de 1024 da legenda conta só o texto visível
    if foto and len(visivel) <= 1000:
        try:
            _telegram("sendPhoto", {"photo": foto, "caption": texto})
            return
        except Exception:
            pass
    _telegram("sendMessage", {"text": texto[:4000], "disable_web_page_preview": "true"})


def enviar_email(assunto, corpo_html):
    usuario = os.environ["EMAIL_USUARIO"]
    msg = EmailMessage()
    msg["Subject"] = assunto
    msg["From"] = f"Alerta de imóveis <{usuario}>"
    msg["To"] = os.environ.get("EMAIL_DESTINO") or usuario
    msg.set_content("Abra este e-mail em um leitor que mostre HTML.")
    msg.add_alternative(corpo_html, subtype="html")
    servidor = os.environ.get("EMAIL_SERVIDOR", "smtp.gmail.com")
    with smtplib.SMTP_SSL(servidor, 465, timeout=30) as s:
        s.login(usuario, os.environ["EMAIL_SENHA_APP"].replace(" ", ""))
        s.send_message(msg)


# ---------- textos ----------

def reais(valor):
    return "R$ " + f"{valor:,.0f}".replace(",", ".")


def endereco(a):
    if not a.get("rua") and a.get("titulo"):
        # sem rua: o título costuma trazer o nome do edifício
        predio = re.search(r"(Edif[íi]cio|Ed\.|Residencial|Condom[íi]nio)\s+[^,|]{3,45}?"
                           r"(?=\s+(?:no|na|com|em|para|próximo)\s|[,|]|$)", a["titulo"])
        rua = predio.group(0).strip() if predio else "Rua não informada"
    else:
        rua = a.get("rua") or "Rua não informada"
    if a.get("numero"):
        rua += f", {a['numero']}"
    return rua + (f" · {a['bairro']}" if a.get("bairro") else "")


def distancia(a, ref_nome):
    if a.get("minutos") is None:
        return "distância não calculada"
    return f"{a['minutos']:.0f} min a pé do {ref_nome} ({a['metros']} m)"


def valores(a):
    partes = [f"Aluguel {reais(a['aluguel'])}"]
    if a.get("condominio"):
        partes.append(f"condomínio {reais(a['condominio'])}")
    if a.get("iptu"):
        partes.append(f"IPTU {reais(a['iptu'])}")
    if len(partes) == 1:
        return partes[0]
    return " + ".join(partes) + f" = {reais(a['total'])}"


def caracteristicas(a):
    partes = []
    if a.get("quartos"):
        partes.append(f"{a['quartos']} quartos")
    if a.get("vagas"):
        partes.append(f"{a['vagas']} vaga" + ("s" if a["vagas"] > 1 else ""))
    if a.get("area"):
        partes.append(f"{a['area']} m²")
    return " · ".join(partes)


def acesso(a):
    if a.get("terreo"):
        return "Anúncio menciona térreo"
    return "Elevador: sim" if a.get("elevador") else "Elevador: não informado"


def origem(a):
    if a.get("anunciante") and a["anunciante"] != a["fonte"]:
        return f"{a['anunciante']} (visto em {a['fonte']})"
    return a["fonte"]


def link_rota(a, ref):
    if a.get("lat") is None:
        return None
    return ("https://www.google.com/maps/dir/?api=1&travelmode=walking"
            f"&origin={a['lat']},{a['lon']}&destination={ref['lat']},{ref['lon']}")


def texto_telegram(a, ref):
    e = html.escape
    titulo = a.get("mudanca") or "Novo apartamento"
    linhas = [
        f"<b>{e(titulo)} · {e(distancia(a, ref['nome']))}</b>",
        e(endereco(a)),
        e(caracteristicas(a)),
        e(valores(a)),
        e(acesso(a)),
        "Anunciante: " + e(origem(a)),
    ]
    linhas += [f"Atenção: {e(aviso)}" for aviso in a.get("avisos", [])]
    links = [f'<a href="{e(a["url"])}">Abrir anúncio</a>']
    if link_rota(a, ref):
        links.append(f'<a href="{e(link_rota(a, ref))}">Rota a pé</a>')
    linhas.append(" · ".join(links))
    return "\n".join(l for l in linhas if l)


def bloco_email(a, ref):
    e = html.escape
    foto = (f'<img src="{e(a["imagem"])}" width="260" style="border-radius:6px;display:block;margin:0 0 8px">'
            if a.get("imagem") else "")
    avisos = "".join(f'<div style="color:#9a5b00">Atenção: {e(x)}</div>' for x in a.get("avisos", []))
    rota = (f' · <a href="{e(link_rota(a, ref))}">Rota a pé</a>' if link_rota(a, ref) else "")
    return (
        '<div style="border:1px solid #ddd;border-radius:8px;padding:14px;margin:0 0 14px;'
        'font-family:Arial,sans-serif;font-size:14px;line-height:1.5;color:#222">'
        f'{foto}<div style="font-size:16px"><b>{e(a.get("mudanca") or "Novo apartamento")} · '
        f'{e(distancia(a, ref["nome"]))}</b></div>'
        f'<div>{e(endereco(a))}</div><div>{e(caracteristicas(a))}</div>'
        f'<div><b>{e(valores(a))}</b></div><div>{e(acesso(a))}</div>'
        f'<div>Anunciante: {e(origem(a))}</div>{avisos}'
        f'<div style="margin-top:8px"><a href="{e(a["url"])}">Abrir anúncio</a>{rota}</div></div>'
    )


def assunto_email(anuncios):
    if len(anuncios) == 1:
        a = anuncios[0]
        return f"Novo apartamento: {endereco(a)} · {reais(a['total'])}"
    return f"{len(anuncios)} novos apartamentos perto do trabalho"


def linha_resumo(a, ref):
    minutos = f"{a['minutos']:.0f} min" if a.get("minutos") is not None else "? min"
    return f"{minutos} · {endereco(a)} · {caracteristicas(a)} · {valores(a)}"


def resumo_telegram(anuncios, ref, titulo):
    e = html.escape
    linhas = [f"<b>{e(titulo)}</b>", f"{len(anuncios)} apartamentos dentro do perfil hoje."]
    for a in anuncios[:12]:
        linhas.append(f'• <a href="{e(a["url"])}">{e(linha_resumo(a, ref))}</a>')
    if len(anuncios) > 12:
        linhas.append(f"… e mais {len(anuncios) - 12}. A lista completa foi para o e-mail.")
    linhas.append("A partir de agora você recebe só os anúncios novos.")
    return "\n".join(linhas)


def resumo_email(anuncios, ref, titulo, introducao=None):
    e = html.escape
    if introducao is None:
        introducao = (f"{len(anuncios)} apartamentos dentro do perfil hoje, do mais perto para o mais longe. "
                      "Nos anúncios do Chaves na Mão desta primeira lista o valor é só o do aluguel. "
                      "A partir de agora você recebe só os anúncios novos.")
    linhas = "".join(
        '<tr><td style="padding:6px 8px;border-bottom:1px solid #eee;white-space:nowrap">'
        f'{(str(round(a["minutos"])) + " min") if a.get("minutos") is not None else "?"}</td>'
        f'<td style="padding:6px 8px;border-bottom:1px solid #eee"><a href="{e(a["url"])}">{e(endereco(a))}</a>'
        f'<br><span style="color:#666">{e(caracteristicas(a))} · {e(origem(a))}'
        + "".join(f" · {e(x)}" for x in a.get("avisos", [])) + "</span></td>"
        f'<td style="padding:6px 8px;border-bottom:1px solid #eee;white-space:nowrap">{e(valores(a))}</td></tr>'
        for a in anuncios)
    return (
        '<div style="font-family:Arial,sans-serif;font-size:14px;color:#222">'
        f"<h2 style=\"font-size:18px\">{e(titulo)}</h2>"
        f"<p>{e(introducao)}</p>"
        f'<table style="border-collapse:collapse;width:100%">{linhas}</table></div>'
    )
