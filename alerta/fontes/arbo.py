"""Sites de imobiliárias feitos na plataforma Arbo.

A página de busca traz, de uma vez, a coordenada e o aluguel de todos os imóveis para
alugar. Os demais dados vêm da página de cada imóvel, aberta só para os que estão perto.
"""
from ..util import baixar, dinheiro, distancia_m, next_data, procurar_dict
from . import inteiro, novo_anuncio


def _completar(a, d):
    a.update(
        url=d.get("url_amiga") or a["url"], titulo=d.get("imv_titulo") or a["titulo"],
        criado_em=(d.get("createdAt") or "")[:10] or None,
        aluguel=dinheiro(d.get("imv_preco_locacao")) or a["aluguel"],
        condominio=dinheiro(d.get("imv_preco_cond")) or None,
        iptu=dinheiro(d.get("imv_preco_iptu")) or None,
        quartos=inteiro(d.get("imv_qtd_dorm")), vagas=inteiro(d.get("imv_qtd_vagas")),
        area=inteiro(d.get("imv_area_util")),
        rua=d.get("imv_endereco"), bairro=d.get("imv_bairro"),
        numero=str(d["imv_end_numero"]) if d.get("imv_end_numero") else None,
    )
    a["aproximado"] = not a["numero"]
    fotos = d.get("fotos") or []
    if fotos:
        a["imagem"] = fotos[0].get("fullsize") or fotos[0].get("imvft_url") or fotos[0].get("thumbnail")
    texto = (d.get("imv_obs") or "").lower()
    if "elevador" in texto:
        a["elevador"] = True
    if "térreo" in texto or "terreo" in texto:
        a["terreo"] = True


def coletar(cfg_fonte, ctx):
    dados = next_data(baixar(cfg_fonte["base"] + "/imoveis/para-alugar/apartamento"))
    if not dados:
        raise RuntimeError("dados da busca não encontrados na página")
    props = dados["props"]["pageProps"]
    ref = ctx["cfg"]["referencia"]
    raio = ctx["cfg"]["criterios"]["raio_busca_m"]
    completos = {d.get("imv_cod_gaia"): d for d in props.get("imoveis") or []}
    anuncios = []
    for ponto in props.get("locations") or []:
        codigo = ponto.get("imv_cod_gaia") or ""
        loc = ponto.get("imv_location") or {}
        if not codigo.startswith("AP") or "lat" not in loc:
            continue
        if distancia_m(ref["lat"], ref["lon"], loc["lat"], loc["lng"]) > raio:
            continue  # longe: nem entra na lista
        a = novo_anuncio(
            cfg_fonte["nome"], codigo, anunciante=cfg_fonte["nome"],
            url=f"{cfg_fonte['base']}/imovel/{codigo}",
            aluguel=dinheiro(ponto.get("imv_preco_locacao")), lat=loc["lat"], lon=loc["lng"])
        if codigo in completos:
            _completar(a, completos[codigo])
            a["_completo"] = True
        anuncios.append(a)
    return anuncios


def detalhar(a, cfg_fonte, ctx):
    if a.pop("_completo", False):
        return
    dados = next_data(baixar(f"{cfg_fonte['base']}/imovel/{a['id']}"))
    d = procurar_dict(dados, lambda x: x.get("imv_cod_gaia") == a["id"] and "imv_qtd_dorm" in x)
    if d:
        _completar(a, d)
