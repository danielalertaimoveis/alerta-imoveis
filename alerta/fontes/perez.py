"""Site da Imobiliária Perez: a lista já traz coordenada, vagas e data de cadastro."""
import re

from ..util import baixar, dinheiro, objeto_em, texto_rsc
from . import inteiro, novo_anuncio


def _ler_pagina(html):
    texto = texto_rsc(html)
    itens = []
    for m in re.finditer(r'\{"id":"[^"]+","code":"[^"]+","title":', texto):
        try:
            itens.append(objeto_em(texto, m.start()))
        except ValueError:
            pass
    links = {codigo: caminho for caminho, codigo in re.findall(r'href="(/imovel/[^"]*-cod-(\d+))"', html)}
    for item in itens:
        item["_caminho"] = links.get(str(item.get("code")))
    paginas = re.search(r'"initialPagination":\{"currentPage":\d+,"totalPages":(\d+)', texto)
    return itens, int(paginas.group(1)) if paginas else 1


def coletar(cfg_fonte, ctx):
    anuncios = {}
    for caminho in cfg_fonte["paginas"]:
        endereco = cfg_fonte["base"] + caminho
        itens, total = _ler_pagina(baixar(endereco))
        for pagina in range(2, min(total, 4) + 1):
            itens += _ler_pagina(baixar(f"{endereco}?page={pagina}"))[0]
        for d in itens:
            if d.get("operationType") != "RENT" or (d.get("propertyTypeName") or "Apartamento") != "Apartamento":
                continue
            fotos = d.get("photos") or []
            a = novo_anuncio(
                cfg_fonte["nome"], d["code"], anunciante=cfg_fonte["nome"],
                url=cfg_fonte["base"] + (d.get("_caminho") or cfg_fonte["paginas"][0]),
                titulo=d.get("title"), imagem=fotos[0].get("url") if fotos else None,
                criado_em=(d.get("createdAt") or "")[:10] or None,
                aluguel=dinheiro(d.get("price")), quartos=inteiro(d.get("bedrooms")),
                vagas=inteiro(d.get("parkingSpaces")), area=inteiro(d.get("builtArea")),
                bairro=d.get("neighborhoodName"), lat=d.get("latitude"), lon=d.get("longitude"),
                aproximado=True,  # o site não mostra rua nem número
            )
            anuncios[a["chave"]] = a
    return list(anuncios.values())
