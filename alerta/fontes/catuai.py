"""Site da Catuaí Imóveis: lista por bairro, do mais caro para o mais barato.

O cartão traz só edifício, bairro, área e aluguel. Quartos, vagas, condomínio e rua vêm
da página do imóvel, aberta apenas para os que cabem no valor. As páginas são pesadas
(quase 2 MB), por isso esta fonte é lida com intervalo maior (ver config).
"""
import re

from ..util import baixar, dinheiro, so_texto
from . import inteiro, novo_anuncio


def coletar(cfg_fonte, ctx):
    anuncios = {}
    for caminho in cfg_fonte["paginas"]:
        endereco = cfg_fonte["base"] + caminho
        pagina, ultima = 1, 1
        while pagina <= min(ultima, 5):
            html = baixar(endereco + (f"?page={pagina}" if pagina > 1 else ""))
            ultima = max([ultima] + [int(n) for n in re.findall(r'href="\?page=(\d+)"', html)])
            partes = re.split(r'href="(/imovel/[^"]+)" class="anchor-image"', html)
            for slug, corpo in zip(partes[1::2], partes[2::2]):
                texto = re.sub(r"(Locação\|Apartamento\|)+", "", so_texto(corpo))
                preco = re.search(r"Locação\|R\$ ([\d.]+,\d\d)", texto)
                campos = texto.split("|")
                if not preco or "apartamento" not in slug or len(campos) < 3:
                    continue
                area = re.search(r"(\d+) m²", texto)
                foto = re.search(r'(?:src|data-lazy)="(https://[^"]+\.(?:jpe?g|webp|png)[^"]*)"', corpo)
                a = novo_anuncio(
                    cfg_fonte["nome"], slug.rsplit("/", 1)[-1], anunciante=cfg_fonte["nome"],
                    url=cfg_fonte["base"] + slug, titulo=campos[1].strip(),
                    imagem=foto.group(1) if foto else None,
                    aluguel=dinheiro(preco.group(1)), area=inteiro(area.group(1)) if area else None,
                    bairro=campos[2].split(" - ")[0].strip(), aproximado=True,
                )
                anuncios.setdefault(a["chave"], a)
            pagina += 1
    if not anuncios:
        raise RuntimeError("nenhum apartamento encontrado nas páginas")
    return list(anuncios.values())


def detalhar(a, cfg_fonte, ctx):
    texto = so_texto(baixar(a["url"]))
    quartos = re.search(r"\|(\d+) Quartos?\|", texto)
    vagas = re.search(r"\|(\d+) Vagas? de garagem\|", texto)
    cond = re.search(r"Condomínio: R\$ ([\d.]+,\d\d)", texto)
    rua = re.search(r"Apartamento EM ((?:Rua|Avenida|Av\.|Travessa|Alameda|R\.)[^,|]+), Londrina", texto)
    a["quartos"] = inteiro(quartos.group(1)) if quartos else a["quartos"]
    a["vagas"] = inteiro(vagas.group(1)) if vagas else None
    a["condominio"] = (dinheiro(cond.group(1)) or None) if cond else None
    a["rua"] = rua.group(1).strip() if rua else None
    if re.search(r"elevador", texto, flags=re.I):
        a["elevador"] = True
    if re.search(r"t[ée]rreo", texto, flags=re.I):
        a["terreo"] = True
