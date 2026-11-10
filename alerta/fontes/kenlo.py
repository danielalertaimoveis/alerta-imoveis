"""Sites de imobiliárias feitos na plataforma Kenlo (lista ordenada pelos mais recentes).

A lista traz aluguel, condomínio, vagas e elevador, mas não a coordenada nem o número
do prédio: o endereço é geocodificado pela rua, então a localização é sempre aproximada.
"""
import json
import math
import re

from ..util import baixar, dinheiro
from . import inteiro, novo_anuncio

POR_PAGINA = 12


def _primeiro(valor):
    return valor[0] if isinstance(valor, list) and valor else valor


def _ler_pagina(html):
    m = re.search(r"window\.markoVars\['listings-[0-9a-z]+'\]\s*=\s*", html)
    if not m:
        raise RuntimeError("lista de imóveis não encontrada na página")
    dados = json.JSONDecoder().raw_decode(html, m.end())[0]
    return dados["settings"]["listings"]


def _anuncio(item, cfg_fonte):
    partes = [p.strip() for p in (item.get("full_address") or "").split(" - ")]
    rua = partes[0] if len(partes) >= 3 else None
    iptu = dinheiro(item.get("property_tax"))
    if iptu is not None:
        iptu = iptu / 12 if item.get("property_tax_payment") == "YEARLY" else iptu
        iptu = round(iptu) if iptu >= 10 else None  # valores simbólicos (0,01) = não informado
    cond = dinheiro(item.get("condo_fees"))
    amenidades = item.get("amenities") or []
    return novo_anuncio(
        cfg_fonte["nome"], item.get("property_full_reference") or item["url"],
        url=cfg_fonte["base"] + item["url"], titulo=item.get("website_title") or item.get("heading1"),
        anunciante=cfg_fonte["nome"], imagem=item.get("picture_full"),
        criado_em=(item.get("updated_at") or "")[:10] or None,
        aluguel=dinheiro(_primeiro(item.get("rent_price"))),
        condominio=cond if cond and cond >= 10 else None, iptu=iptu,
        quartos=inteiro(_primeiro(item.get("bedrooms"))), vagas=inteiro(_primeiro(item.get("garages"))),
        area=inteiro(_primeiro(item.get("area"))),
        rua=rua, bairro=item.get("neighborhood"), aproximado=True,
        elevador=True if "ELEVATOR" in amenidades else None,
    )


def coletar(cfg_fonte, ctx):
    endereco = cfg_fonte["base"] + cfg_fonte["caminho"]
    lista = _ler_pagina(baixar(endereco))
    itens = list(lista.get("data") or [])
    total_paginas = math.ceil((lista.get("count") or 0) / POR_PAGINA)
    # primeira vez: lê tudo; depois, só as duas primeiras páginas (os mais recentes)
    ate = total_paginas if ctx["primeira_vez"] else min(2, total_paginas)
    for pagina in range(2, ate + 1):
        itens += _ler_pagina(baixar(f"{endereco}?pagina={pagina}")).get("data") or []
    anuncios = {}
    for item in itens:
        if item.get("property_type") not in (None, "APARTMENT"):
            continue
        if (item.get("city") or "Londrina") != "Londrina":
            continue
        a = _anuncio(item, cfg_fonte)
        anuncios[a["chave"]] = a
    return list(anuncios.values())
