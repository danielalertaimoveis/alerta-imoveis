"""Sites feitos na plataforma Vista (ex.: JR3, Cube): lista com 12 imóveis por página,
os cadastrados mais recentemente primeiro, e filtro de bairro pelo endereço da busca."""
import re

from ..util import baixar, dinheiro, objeto_em, texto_rsc
from . import inteiro, novo_anuncio


def _ler_pagina(html):
    texto = texto_rsc(html)
    i = texto.find('"properties":[')
    if i < 0:
        return [], 0
    imoveis = objeto_em(texto, i + len('"properties":'))
    total = re.search(r'"total":(\d+),"page":\d+', texto[i:])
    return imoveis, int(total.group(1)) if total else 0


def coletar(cfg_fonte, ctx):
    anuncios = {}
    for caminho in cfg_fonte["paginas"]:
        endereco = cfg_fonte["base"] + caminho
        html = baixar(endereco)
        imoveis, total = _ler_pagina(html)
        paginas = -(-total // 12)
        ate = min(paginas, 8) if ctx.get("completa") else min(paginas, 2)
        for pagina in range(2, ate + 1):
            mais = baixar(f"{endereco}&page={pagina}")
            html += mais
            imoveis += _ler_pagina(mais)[0]
        for d in imoveis:
            if d.get("Categoria") != "Apartamento" or not d.get("ValorLocacao"):
                continue
            cod = str(d["Codigo"])
            link = re.search(r'href="(/imovel/[^"]*?%s)"' % re.escape(cod), html)
            rua = " ".join(p for p in (d.get("TipoEndereco"), d.get("Endereco")) if p) or None
            tem_mapa = d.get("Latitude") not in (None, 0, "0", "")
            a = novo_anuncio(
                cfg_fonte["nome"], cod, anunciante=cfg_fonte["nome"],
                url=cfg_fonte["base"] + (link.group(1) if link else caminho),
                titulo=d.get("TituloSite"), imagem=d.get("FotoDestaque"),
                criado_em=(d.get("DataCadastro") or "")[:10] or None,
                aluguel=dinheiro(d.get("ValorLocacao")),
                quartos=inteiro(d.get("Dormitorios")), vagas=inteiro(d.get("Vagas")),
                area=inteiro(d.get("AreaPrivativa")),
                rua=rua, bairro=(d.get("Bairro") or "").strip().title() or None,
                lat=float(d["Latitude"]) if tem_mapa else None,
                lon=float(d["Longitude"]) if tem_mapa else None,
                aproximado=True,  # a lista não traz o número do prédio
            )
            anuncios.setdefault(a["chave"], a)
    if not anuncios:
        raise RuntimeError("nenhum apartamento encontrado nas páginas")
    return list(anuncios.values())
