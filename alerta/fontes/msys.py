"""Sites feitos na plataforma Msys (ex.: Raul Fulgêncio, Serenity).

A página pública de aluguel mostra só os 12 imóveis do topo da lista, de todos os tipos,
e não aceita filtro pelo endereço. A cobertura é parcial: pega o que entra no topo.
"""
import re

from ..util import baixar, dinheiro, next_data, procurar_dict
from . import inteiro, novo_anuncio


def coletar(cfg_fonte, ctx):
    html = baixar(cfg_fonte["base"] + "/alugar/todos")
    dados = next_data(html)
    lista = procurar_dict(dados, lambda d: "initialPropertys" in d) if dados else None
    if not lista:
        raise RuntimeError("lista de imóveis não encontrada na página")
    links = {cod: caminho for caminho, cod in re.findall(r'href="(/imovel/[^"]*/(\d+))"', html)}
    anuncios = []
    for d in lista["initialPropertys"].get("docs") or []:
        if d.get("namCategory") != "Apartamentos" or d.get("namCity") != "Londrina":
            continue
        cod = str(d["idtProperty"])
        fotos = re.search(r'"urlPhoto":"([^"]+)"', d.get("jsonPhotos") or "")
        mostra_mapa = d.get("flgShowMapSite") and d.get("latitude")
        anuncios.append(novo_anuncio(
            cfg_fonte["nome"], cod, anunciante=cfg_fonte["nome"],
            url=cfg_fonte["base"] + links.get(cod, "/alugar/todos"),
            titulo=d.get("desTitleSite"), imagem=fotos.group(1) if fotos else None,
            aluguel=dinheiro(d.get("valLocation")),
            condominio=dinheiro(d.get("valCondominium")) or None,
            iptu=dinheiro(d.get("valMonthIptu")) or None,
            quartos=inteiro(d.get("prop_char_5")), vagas=inteiro(d.get("totalGarages")),
            area=inteiro(d.get("prop_char_2")),
            rua=d.get("namStreet"), bairro=d.get("namDistrict"),
            lat=float(d["latitude"]) if mostra_mapa else None,
            lon=float(d["longitude"]) if mostra_mapa else None,
            aproximado=True,  # o site não mostra o número do prédio
        ))
    return anuncios
