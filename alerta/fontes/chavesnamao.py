"""Chaves na Mão: usa a busca por área do mapa, que devolve os anúncios com coordenada.

Uma chamada por execução. Grupos grandes (um prédio com muitos anúncios) vêm sem a
lista; para esses, abre-se a página de resultados centrada no grupo, e só quando a
quantidade do grupo muda.
"""
import json
import re

from ..util import baixar, blocos_ld_json, caixa, dinheiro, distancia_m, texto_rsc
from . import inteiro, novo_anuncio

SITE = "https://www.chavesnamao.com.br"
FOTO = SITE + "/imn/0400X0262/N/60/imoveis/"


def _parametros(cfg_fonte, criterios):
    return (f"level1=apartamentos-para-alugar&level2={cfg_fonte['cidade']}"
            f"&level3={criterios['quartos_min']}-quartos", f"filtro=pmax:{criterios['valor_total_max']}")


def _do_mapa(item):
    bairro = (item.get("location") or "").split(",")[0].strip() or None
    numero = str(item.get("addressNumber") or "").strip()
    numero = numero if re.fullmatch(r"\d+\w?", numero) else None
    return novo_anuncio(
        "Chaves na Mão", item["id"],
        url=SITE + item["url"], titulo=item.get("title"),
        imagem=FOTO + item["image"] if item.get("image") else None,
        aluguel=dinheiro(item.get("price")), quartos=inteiro(item.get("bedrooms")),
        vagas=inteiro(item.get("garages")), area=inteiro(item.get("area")),
        rua=item.get("street"), numero=numero, bairro=bairro,
        lat=item.get("lat"), lon=item.get("lon"),
        aproximado=bool(item.get("approximateLocation")) or not numero,
    )


def _da_pagina(oferta, aproximado):
    imovel = oferta.get("itemOffered", {})
    end = imovel.get("address", {})
    geo = imovel.get("geo") or {}
    url = oferta.get("url", "")
    m = re.search(r"id-(\d+)", url)
    if not m:
        return None
    rua, _, numero = (end.get("streetAddress") or "").rpartition(",")
    numero = numero.strip()
    if not rua:  # sem vírgula: só o nome da rua
        rua, numero = numero, ""
    if not re.fullmatch(r"\d+\w?", numero):
        numero = ""
    area = re.search(r"\d+", (imovel.get("floorSize") or {}).get("unitText") or "")
    return novo_anuncio(
        "Chaves na Mão", m.group(1),
        url=url, titulo=oferta.get("name"), imagem=imovel.get("image"),
        anunciante=(oferta.get("offeredBy") or {}).get("name"),
        aluguel=dinheiro(oferta.get("price")), quartos=inteiro(imovel.get("numberOfBedrooms")),
        vagas=1 if "com-garagem" in url else None, area=inteiro(area.group(0)) if area else None,
        rua=rua.strip() or None, numero=numero or None, bairro=end.get("addressLocality"),
        lat=float(geo["latitude"]) if geo.get("latitude") else None,
        lon=float(geo["longitude"]) if geo.get("longitude") else None,
        aproximado=aproximado or not numero,
    )


def _pagina_do_grupo(grupo, base, filtro, ctx):
    """Anúncios de um grupo que veio sem lista: a página ordena por distância ao centro do mapa."""
    achados = []
    folga = 0.0004
    b = grupo["bounds"]
    for pg in range(1, 1 + (grupo["count"] + 6) // 15 + 1):
        url = (f"{SITE}/apartamentos-para-alugar/{base['cidade']}/{base['quartos']}-quartos/"
               f"?mapNorth={b['north'] + folga:.5f}&mapSouth={b['south'] - folga:.5f}"
               f"&mapEast={b['east'] + folga:.5f}&mapWest={b['west'] - folga:.5f}"
               f"&locationScope=area&zoom=19&{filtro}" + (f"&pg={pg}" if pg > 1 else ""))
        html = baixar(url)
        ofertas = []
        for bloco in blocos_ld_json(html):
            if isinstance(bloco, dict) and bloco.get("@type") == "RealEstateListing":
                ofertas = (bloco.get("offers") or {}).get("itemListElement") or []
        fora = 0
        for oferta in ofertas:
            a = _da_pagina(oferta, aproximado=bool(grupo.get("approximate")))
            if not a or a["lat"] is None:
                continue
            if distancia_m(grupo["lat"], grupo["lon"], a["lat"], a["lon"]) <= 90:
                achados.append(a)
            else:
                fora += 1
        if not ofertas or fora:  # já passou dos anúncios deste ponto
            break
    return achados


def coletar(cfg_fonte, ctx):
    criterios = ctx["cfg"]["criterios"]
    ref = ctx["cfg"]["referencia"]
    niveis, filtro = _parametros(cfg_fonte, criterios)
    n, s, e, w = caixa(ref["lat"], ref["lon"], criterios["raio_busca_m"])
    url = (f"{SITE}/api/realestate/search-map-clusters/?{niveis}"
           f"&mapNorth={n:.5f}&mapSouth={s:.5f}&mapEast={e:.5f}&mapWest={w:.5f}"
           f"&locationScope=area&zoom=19&{filtro}")
    dados = json.loads(baixar(url, aceitar="application/json"))
    if "clusters" not in dados:
        raise RuntimeError("resposta do mapa em formato inesperado")

    anuncios = {}
    grupos_vistos = ctx["estado"].setdefault("cnm_grupos", {})
    grupos_agora = {}
    base = {"cidade": cfg_fonte["cidade"], "quartos": criterios["quartos_min"]}
    for grupo in dados.get("clusters", []) + dados.get("approxAreas", []):
        itens = grupo.get("listings") or []
        for item in itens:
            a = _do_mapa(item)
            if grupo.get("approximate"):
                a["aproximado"] = True
            anuncios[a["chave"]] = a
        if grupo.get("count", 0) > len(itens):
            # grupo sem lista completa: só reabre a página se a quantidade mudou
            gid = grupo["id"]
            grupos_agora[gid] = grupo["count"]
            if grupos_vistos.get(gid) != grupo["count"] or ctx.get("completa"):
                try:
                    for a in _pagina_do_grupo(grupo, base, filtro, ctx):
                        anuncios.setdefault(a["chave"], a)
                except Exception as erro:
                    ctx["log"](f"  Chaves na Mão: grupo {gid} não pôde ser aberto ({erro})")
                    grupos_agora.pop(gid)  # tenta de novo na próxima
    ctx["estado"]["cnm_grupos"] = grupos_agora
    return list(anuncios.values())


def detalhar(a, cfg_fonte, ctx):
    """Completa condomínio, elevador, anunciante e data a partir da página do anúncio."""
    html = baixar(a["url"])
    texto = texto_rsc(html)
    caminho = a["url"].replace(SITE, "")
    pos = texto.find(f'"url":"{caminho}","prices":')
    if pos >= 0:
        try:
            precos = json.loads(re.search(r'"prices":(\{[^{}]*\})', texto[pos:pos + 600]).group(1))
            cond = dinheiro(precos.get("condominiumFee")) if "R$" in str(precos.get("condominiumFee")) else None
            iptu = dinheiro(precos.get("iptuValue")) if "R$" in str(precos.get("iptuValue")) else None
            a["condominio"] = cond if cond is not None else a["condominio"]
            a["iptu"] = iptu if iptu is not None else a["iptu"]
        except (AttributeError, ValueError):
            pass
    m = re.search(r'<meta name="description" content="([^"]*)"', html)
    desc = m.group(1) if m else ""
    m = re.search(r"Falar com (.+?), ref", desc)
    if m and not a["anunciante"]:
        a["anunciante"] = m.group(1).strip()
    m = re.search(r"(\d+) garage", desc)
    if m and a["vagas"] is None:
        a["vagas"] = int(m.group(1))
    if re.search(r'"name":"Elevador', texto):
        a["elevador"] = True
    m = re.search(r'"createdAt":"(\d{4}-\d\d-\d\d)', texto)
    if m:
        a["criado_em"] = m.group(1)
    m = re.search(r'"segment":"REALTY","description":"((?:[^"\\]|\\.)*)"', texto)
    if m and re.search(r"t[ée]rreo", m.group(1), flags=re.I):
        a["terreo"] = True
