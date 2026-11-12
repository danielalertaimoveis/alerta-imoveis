"""Sites feitos na plataforma Flip (ex.: Century 21 Class).

Cada página de busca traz até 30 imóveis com coordenada, condomínio e vagas. Não há como
pedir a página seguinte sem a API interna do site, então usa-se uma página por bairro.
"""
from ..util import baixar, dinheiro, next_data
from . import inteiro, novo_anuncio


def coletar(cfg_fonte, ctx):
    anuncios = {}
    for caminho in cfg_fonte["paginas"]:
        dados = next_data(baixar(cfg_fonte["base"] + caminho))
        try:
            imoveis = dados["props"]["pageProps"]["initialBuscarData"]["imoveis"] or []
        except (KeyError, TypeError):
            raise RuntimeError("lista de imóveis não encontrada na página")
        for d in imoveis:
            if d.get("tipoImovel") != "Apartamento" or not d.get("codigo"):
                continue
            det = d.get("detalhes") or {}
            numero = str(d.get("numero") or "").strip()
            numero = numero if numero.isdigit() else None
            caracteristicas = " ".join(d.get("caracteristicas") or []).lower()
            a = novo_anuncio(
                cfg_fonte["nome"], d["codigo"], anunciante=cfg_fonte["nome"],
                url=f"{cfg_fonte['base']}/imoveis/{d.get('imovelUrl')}",
                titulo=d.get("titulo"), imagem=d.get("image") or d.get("thumbnail"),
                aluguel=dinheiro(d.get("precoLocacao") or d.get("preco")),
                condominio=dinheiro(det.get("valorCondominio")) or None,
                quartos=inteiro(det.get("dormitorios")), vagas=inteiro(det.get("vagas")),
                area=inteiro(det.get("areaUtil")),
                rua=d.get("endereco"), numero=numero, bairro=d.get("bairro"),
                lat=d.get("lat"), lon=d.get("lon"),
                aproximado=d.get("showAddress") != "COMPLETO" or not numero,
                elevador=True if "elevador" in caracteristicas else None,
            )
            anuncios[a["chave"]] = a
    return list(anuncios.values())
