"""Site da Alugaflex: uma página lista todos os imóveis de Londrina, com rua, bairro e coordenada."""
import re

from ..util import baixar, dinheiro, so_texto
from . import inteiro, novo_anuncio


def coletar(cfg_fonte, ctx):
    html = baixar(cfg_fonte["base"] + cfg_fonte["caminho"])
    anuncios = {}
    for cartao in re.split(r'<div data-div="prop"', html)[1:]:
        cod = re.search(r"/imovel/(AF\d+)/", cartao)
        titulo = re.search(r'data-div="desc"[^>]*>(.*?)</div>', cartao, flags=re.S)
        if not cod or not titulo:
            continue
        titulo = so_texto(titulo.group(1)).replace("|", " ")
        if not titulo.startswith("Apartamento"):
            continue
        ender = re.search(r'data-div="addr"[^>]*>(.*?)</div>', cartao, flags=re.S)
        partes = [p.strip() for p in so_texto(ender.group(1)).split(" - ")] if ender else []
        quartos = re.search(r"(\d+)\s*quartos?", titulo)
        area = re.search(r"(\d+)\s*m²", titulo)
        preco = re.search(r"Aluguel\s*R\$\s*([\d.]+,\d\d)", so_texto(cartao))
        foto = re.search(r"url\((?:&quot;|['\"])?(https://[^&'\")]+)", cartao)
        lat = re.search(r'data-input="lat"[^>]*value="(-?[\d.]+)"', cartao)
        lon = re.search(r'data-input="lng"[^>]*value="(-?[\d.]+)"', cartao)
        a = novo_anuncio(
            cfg_fonte["nome"], cod.group(1), anunciante=cfg_fonte["nome"],
            url=f"{cfg_fonte['base']}/imovel/{cod.group(1)}/", titulo=re.sub(r"\s+", " ", titulo),
            imagem=foto.group(1) if foto else None,
            aluguel=dinheiro(preco.group(1)) if preco else None,
            quartos=inteiro(quartos.group(1)) if quartos else None,
            area=inteiro(area.group(1)) if area else None,
            rua=partes[0] if len(partes) >= 3 else None,
            bairro=partes[1] if len(partes) >= 3 else None,
            lat=float(lat.group(1)) if lat else None, lon=float(lon.group(1)) if lon else None,
            aproximado=True,  # o site não mostra o número do prédio
        )
        anuncios[a["chave"]] = a
    if not anuncios:
        raise RuntimeError("nenhum apartamento encontrado na página")
    return list(anuncios.values())
