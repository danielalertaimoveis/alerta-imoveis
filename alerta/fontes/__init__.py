"""Coletores de anúncios. Cada módulo expõe coletar() e, se fizer sentido, detalhar()."""
from ..util import normalizar


def novo_anuncio(fonte, id_, **campos):
    """Anúncio no formato comum a todas as fontes. Campo None = informação desconhecida."""
    a = {
        "fonte": fonte, "id": str(id_), "chave": f"{normalizar(fonte).replace(' ', '-')}:{id_}",
        "url": None, "titulo": None, "anunciante": None, "imagem": None, "criado_em": None,
        "aluguel": None, "condominio": None, "iptu": None,
        "quartos": None, "vagas": None, "area": None,
        "rua": None, "numero": None, "bairro": None,
        "lat": None, "lon": None, "aproximado": False,
        "elevador": None, "terreo": None,
    }
    a.update(campos)
    if a["rua"] and normalizar(a["rua"]) in ("nao disponivel", "nao informado", "nao informada"):
        a["rua"] = None
    if a["area"] is not None and a["area"] < 15:  # 0 ou 1 m² = campo não preenchido
        a["area"] = None
    for campo in ("condominio", "iptu"):  # R$ 0,01 ou R$ 1 = campo não preenchido
        if a[campo] is not None and a[campo] < 10:
            a[campo] = None
    return a


def inteiro(valor):
    try:
        return int(float(valor))
    except (TypeError, ValueError):
        return None
