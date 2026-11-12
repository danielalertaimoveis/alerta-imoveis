"""Funções de apoio: download, distância, rota a pé, geocodificação e leitura de páginas."""
import html as html_lib
import json
import math
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

UA_NAVEGADOR = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
UA_SERVICOS = "alerta-imoveis/1.0 (monitor pessoal de aluguel)"

_ultimo_acesso = {}


def baixar(url, pausa=1.2, timeout=40, tentativas=2, ua=UA_NAVEGADOR, aceitar="text/html,application/json;q=0.9,*/*;q=0.8"):
    """Baixa uma URL como texto, respeitando uma pausa mínima entre acessos ao mesmo site."""
    host = urllib.parse.urlsplit(url).netloc
    erro = None
    for tentativa in range(tentativas):
        espera = pausa - (time.time() - _ultimo_acesso.get(host, 0))
        if espera > 0:
            time.sleep(espera)
        _ultimo_acesso[host] = time.time()
        req = urllib.request.Request(url, headers={
            "User-Agent": ua, "Accept": aceitar, "Accept-Language": "pt-BR,pt;q=0.9"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                dados = r.read()
                # alguns sites antigos usam ISO-8859-1: respeita o que o site declara
                codificacao = r.headers.get_content_charset()
                if not codificacao:
                    m = re.search(rb'charset=["\']?([\w-]+)', dados[:3000])
                    codificacao = m.group(1).decode("ascii") if m else "utf-8"
                try:
                    return dados.decode(codificacao, errors="ignore")
                except LookupError:
                    return dados.decode("utf-8", errors="ignore")
        except urllib.error.HTTPError as e:
            erro = e
            if e.code in (403, 404, 410, 429):
                break  # insistir só piora um bloqueio
        except Exception as e:  # rede, tempo esgotado
            erro = e
        time.sleep(2 + 2 * tentativa)
    raise RuntimeError(f"falha ao acessar {url}: {erro}")


def distancia_m(lat1, lon1, lat2, lon2):
    """Distância em linha reta, em metros."""
    r = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 2 * r * math.asin(math.sqrt(a))


def caixa(lat, lon, raio_m):
    """Retângulo (norte, sul, leste, oeste) que contém o círculo de raio dado."""
    dlat = raio_m / 111320
    dlon = raio_m / (111320 * math.cos(math.radians(lat)))
    return lat + dlat, lat - dlat, lon + dlon, lon - dlon


def normalizar(texto):
    """Minúsculas, sem acento e sem pontuação: para comparar nomes de rua e bairro."""
    t = unicodedata.normalize("NFKD", texto or "")
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def dinheiro(valor):
    """Converte 'R$ 2.300' ou 2300.0 em float. Devolve None se não houver valor."""
    if valor is None:
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    m = re.search(r"\d[\d.]*(?:,\d+)?", str(valor))
    if not m:
        return None
    return float(m.group(0).replace(".", "").replace(",", "."))


def so_texto(trecho_html):
    """Texto visível de um trecho de HTML, com as partes separadas por '|'."""
    t = re.sub(r"<(script|style|svg)\b.*?</\1>", "", trecho_html, flags=re.S)
    t = html_lib.unescape(re.sub(r"<[^>]+>", "|", t))
    return re.sub(r"\s*(\|\s*)+", "|", re.sub(r"[ \t\r\n]+", " ", t)).strip("| ")


def blocos_ld_json(html):
    """Todos os blocos JSON-LD de uma página."""
    saida = []
    for m in re.finditer(r'<script[^>]*type="?application/ld\+json"?[^>]*>(.*?)</script>', html, flags=re.S):
        try:
            saida.append(json.loads(m.group(1)))
        except ValueError:
            pass
    return saida


def next_data(html):
    """Conteúdo de __NEXT_DATA__ (sites Next.js antigos)."""
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, flags=re.S)
    return json.loads(m.group(1)) if m else None


def texto_rsc(html):
    """Junta os trechos self.__next_f.push([1,"..."]) já sem escape (sites Next.js novos)."""
    partes = []
    for m in re.finditer(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)', html):
        try:
            partes.append(json.loads(m.group(1)))
        except ValueError:
            pass
    return "".join(partes)


def objeto_em(texto, posicao):
    """Lê o objeto JSON que começa em texto[posicao]."""
    return json.JSONDecoder().raw_decode(texto, posicao)[0]


def procurar_dict(obj, teste, limite=12):
    """Primeiro dicionário, em qualquer profundidade, para o qual teste(d) é verdadeiro."""
    if limite < 0:
        return None
    if isinstance(obj, dict):
        if teste(obj):
            return obj
        filhos = obj.values()
    elif isinstance(obj, list):
        filhos = obj
    else:
        return None
    for f in filhos:
        achado = procurar_dict(f, teste, limite - 1)
        if achado is not None:
            return achado
    return None


def minutos_a_pe(origem, destino, cache):
    """Tempo de caminhada (min) e distância (m) pela rua. Usa o roteador público do OpenStreetMap.

    Se o roteador falhar, estima a partir da linha reta (ruas ~25% mais longas, 75 m/min).
    """
    chave = f"{destino[0]:.5f},{destino[1]:.5f}"
    if chave in cache:
        return tuple(cache[chave])
    url = ("https://routing.openstreetmap.de/routed-foot/route/v1/foot/"
           f"{origem[1]:.6f},{origem[0]:.6f};{destino[1]:.6f},{destino[0]:.6f}?overview=false")
    try:
        d = json.loads(baixar(url, pausa=1.0, timeout=20, ua=UA_SERVICOS))
        rota = d["routes"][0]
        resultado = (round(rota["duration"] / 60, 1), round(rota["distance"]))
        cache[chave] = list(resultado)
        return resultado
    except Exception:
        reta = distancia_m(origem[0], origem[1], destino[0], destino[1])
        return round(reta * 1.25 / 75, 1), round(reta * 1.25)  # estimativa: não vai para o cache


def geocodificar(rua, cidade, cache):
    """Coordenada aproximada de uma rua (sem número). Devolve (lat, lon) ou None."""
    chave = normalizar(f"{rua} {cidade}")
    if chave in cache:
        return tuple(cache[chave]) if cache[chave] else None
    consulta = urllib.parse.urlencode({
        "street": rua, "city": cidade, "state": "Paraná", "country": "Brasil",
        "format": "json", "limit": 1,
        # só aceita resultado dentro da área urbana de Londrina (há ruas homônimas em outras cidades)
        "viewbox": "-51.30,-23.20,-51.05,-23.45", "bounded": 1})
    try:
        d = json.loads(baixar("https://nominatim.openstreetmap.org/search?" + consulta,
                              pausa=1.3, timeout=20, ua=UA_SERVICOS))
    except Exception:
        return None  # falha de rede: tenta de novo em outra execução
    cache[chave] = [float(d[0]["lat"]), float(d[0]["lon"])] if d else None
    return tuple(cache[chave]) if cache[chave] else None
