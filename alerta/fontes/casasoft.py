"""Sites feitos na plataforma Casasoft (ex.: Veneza, com coordenada no cartão; Atual, sem).

Cada página mostra só os 12 primeiros imóveis, do mais caro para o mais barato; o site
carrega o resto sob demanda. Por isso usam-se páginas estreitas (bairro + nº de quartos),
que cabem quase inteiras em 12.
"""
import re

from ..util import baixar, so_texto
from . import inteiro, novo_anuncio


def coletar(cfg_fonte, ctx):
    anuncios = {}
    for caminho in cfg_fonte["paginas"]:
        html = baixar(cfg_fonte["base"] + caminho)
        for cartao in re.split(r'<div class="properties__card"', html)[1:]:
            ref = re.search(r'data-reference="([^"]+)"', cartao)
            link = re.search(r'href="(/imovel/[^"]+)"', cartao)
            if not ref or not link or "/imovel/apartamento" not in link.group(1):
                continue
            slug = link.group(1)
            preco = re.search(r"locacao-rs-(\d+)", slug)
            quartos = re.search(r"-(\d+)-quartos?-", slug)
            vagas = re.search(r"-(\d+)-vagas?-", slug)
            area = re.search(r"-(\d+)m2-", slug)
            lat = re.search(r'data-latitude="(-?[\d.]+)"', cartao)
            lon = re.search(r'data-longitude="(-?[\d.]+)"', cartao)
            # endereço no cartão: "R. Prefeito Hugo Cabral, 1065 - Centro"
            ender = re.search(r"\|([^|]+?),\s*(\d+)\s*-\s*([^|]+)\|", so_texto(cartao))
            foto = re.search(r'<img[^>]+src="(https://[^"]+)"', cartao)
            a = novo_anuncio(
                cfg_fonte["nome"], ref.group(1), anunciante=cfg_fonte["nome"],
                url=cfg_fonte["base"] + slug, imagem=foto.group(1) if foto else None,
                aluguel=float(preco.group(1)) if preco else None,
                quartos=inteiro(quartos.group(1)) if quartos else None,
                vagas=inteiro(vagas.group(1)) if vagas else None,
                area=inteiro(area.group(1)) if area else None,
                rua=ender.group(1).strip() if ender else None,
                numero=ender.group(2) if ender else None,
                bairro=ender.group(3).strip() if ender else None,
                lat=float(lat.group(1)) if lat else None, lon=float(lon.group(1)) if lon else None,
                aproximado=not ender,
            )
            anuncios[a["chave"]] = a
        # layout antigo da plataforma (ex.: Imobiliária Atual): sem cartão com coordenada,
        # os dados saem do próprio endereço do anúncio
        for slug, preco, ref in re.findall(
                r'href="(/imovel/apartamento[^"?]*-locacao-rs-(\d+))\?id=\d+&(?:amp;)?ref=([\d.]+)', html):
            quartos = re.search(r"apartamento-(\d+)-quartos?-(.+?)-londrina", slug)
            area = re.search(r"-(\d+)m2-", slug)
            a = novo_anuncio(
                cfg_fonte["nome"], ref, anunciante=cfg_fonte["nome"],
                url=cfg_fonte["base"] + slug, aluguel=float(preco),
                quartos=inteiro(quartos.group(1)) if quartos else None,
                vagas=1 if "com-garagem" in slug else None,
                area=inteiro(area.group(1)) if area else None,
                bairro=quartos.group(2).replace("-", " ").title() if quartos else None,
                aproximado=True,
            )
            anuncios.setdefault(a["chave"], a)
    if not anuncios:
        raise RuntimeError("nenhum apartamento encontrado nas páginas")
    return list(anuncios.values())
