"""Site da Imobiliária Santamérica: lista ordenada do mais novo para o mais antigo.

A lista não traz rua nem coordenada, só o bairro. Por isso os alertas desta fonte saem
com "distância não calculada" e valem pelos bairros próximos definidos no config.
"""
import re

from ..util import baixar, dinheiro, so_texto
from . import inteiro, novo_anuncio


def _ler_pagina(html, cfg_fonte):
    anuncios = []
    for cartao in re.split(r'<div class="card card-imo"', html)[1:]:
        cod = re.search(r"<strong>(\d+)</strong>", cartao)
        preco = re.search(r"R\$\s*([\d.]+,\d\d)\s*L", cartao)
        if not cod or not preco:
            continue
        link = re.search(r'href="(/alugar/[^"]*/%s)"' % cod.group(1), cartao)
        titulo = re.search(r'<h2 title="([^"]*)"', cartao)
        bairro = re.search(r'class="card-bairro-cidade">(.*?)</div>\s*</div>', cartao, flags=re.S)
        bairro = so_texto(bairro.group(1)).split(" - ")[0].strip() if bairro else None
        quartos = re.search(r'title="(\d+) Dormit', cartao)
        vagas = re.search(r'title="(\d+) Garage', cartao)
        area = re.search(r'class="a-util-ico[^>]*title="([\d.]+) M', cartao)
        foto = re.search(r'data-flickity-lazyload-src="([^"]+)"', cartao)
        if not link or "/Apartamento/" not in link.group(1):
            continue
        anuncios.append(novo_anuncio(
            cfg_fonte["nome"], cod.group(1), anunciante=cfg_fonte["nome"],
            url=cfg_fonte["base"] + link.group(1),
            titulo=so_texto(titulo.group(1)) if titulo else None, imagem=foto.group(1) if foto else None,
            aluguel=dinheiro(preco.group(1)), quartos=inteiro(quartos.group(1)) if quartos else None,
            # o site mostra o ícone de garagem só quando há vaga
            vagas=inteiro(vagas.group(1)) if vagas else 0,
            area=inteiro(area.group(1)) if area else None, bairro=bairro or None, aproximado=True,
        ))
    return anuncios


def coletar(cfg_fonte, ctx):
    anuncios = {}
    for caminho in cfg_fonte["paginas"]:
        endereco = cfg_fonte["base"] + caminho
        ate = 4 if ctx.get("completa") else 1  # fora da leitura completa, só os mais novos
        for pagina in range(1, ate + 1):
            lidos = _ler_pagina(baixar(endereco + (f"?pag={pagina}" if pagina > 1 else "")), cfg_fonte)
            for a in lidos:
                anuncios.setdefault(a["chave"], a)
            if len(lidos) < 20:
                break
    if not anuncios:
        raise RuntimeError("nenhum anúncio encontrado nas páginas")
    return list(anuncios.values())


def detalhar(a, cfg_fonte, ctx):
    texto = so_texto(baixar(a["url"])).lower()
    if "elevador" in texto:
        a["elevador"] = True
    if re.search(r"t[ée]rreo", texto):
        a["terreo"] = True
    cond = re.search(r"condom[íi]nio[^|]{0,30}\|?\s*r\$\s*([\d.]+,\d\d)", texto)
    if cond:
        a["condominio"] = dinheiro(cond.group(1)) or None
