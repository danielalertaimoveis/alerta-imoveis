"""Monitor de apartamentos para alugar perto de um ponto de referência.

Uso:
    python monitor.py                  uma verificação completa, com envio dos alertas
    python monitor.py --sem-enviar     mostra na tela o que seria enviado e não grava nada
    python monitor.py --teste          envia uma mensagem de teste pelo Telegram e pelo e-mail
"""
import argparse
import json
import os
import sys
import time
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

from alerta import notificar
from alerta.fontes import (alugaflex, arbo, casasoft, catuai, chavesnamao, flip, kenlo, msys,
                           perez, santamerica, vista)
from alerta.util import distancia_m, geocodificar, minutos_a_pe, normalizar

RAIZ = Path(__file__).parent
ARQ_ESTADO = Path(os.environ.get("ALERTA_ESTADO") or RAIZ / "estado" / "estado.json")
FONTES = {"chavesnamao": chavesnamao, "kenlo": kenlo, "arbo": arbo, "perez": perez,
          "flip": flip, "santamerica": santamerica, "alugaflex": alugaflex, "casasoft": casasoft,
          "msys": msys, "catuai": catuai, "vista": vista}
BRASILIA = timezone(timedelta(hours=-3))


def log(texto):
    print(texto, flush=True)


def carregar_env():
    """Lê um arquivo .env local (CHAVE=valor), usado só para testes no computador."""
    arq = RAIZ / ".env"
    if arq.exists():
        for linha in arq.read_text(encoding="utf-8").splitlines():
            if "=" in linha and not linha.strip().startswith("#"):
                chave, valor = linha.split("=", 1)
                os.environ.setdefault(chave.strip(), valor.strip())


def carregar_estado():
    if ARQ_ESTADO.exists():
        return json.loads(ARQ_ESTADO.read_text(encoding="utf-8"))
    return {}


def salvar_estado(estado):
    ARQ_ESTADO.parent.mkdir(exist_ok=True)
    ARQ_ESTADO.write_text(json.dumps(estado, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")


# ---------- regras ----------

def pre_filtro(a, cfg):
    """Descarta com o que já se sabe, antes de gastar acessos com detalhes. Devolve o motivo ou None."""
    c, ref = cfg["criterios"], cfg["referencia"]
    if a["aluguel"] is None:
        return "sem valor de aluguel"
    if a["aluguel"] > c["valor_total_max"]:
        return "aluguel acima do limite"
    if a["quartos"] is not None and a["quartos"] < c["quartos_min"]:
        return "quartos a menos"
    if c["exigir_garagem"] and a["vagas"] == 0:
        return "sem garagem"
    if a["bairro"] and normalizar(a["bairro"]) in {normalizar(b) for b in c.get("bairros_distantes", [])}:
        return "bairro distante (a coordenada do anúncio está errada)"
    if a["lat"] is not None:
        if distancia_m(ref["lat"], ref["lon"], a["lat"], a["lon"]) > c["raio_busca_m"]:
            return "longe"
    elif a["bairro"] and normalizar(a["bairro"]) not in {normalizar(b) for b in c["bairros_proximos"]}:
        return "bairro fora da região"
    return None


def avaliar(a, cfg, estado):
    """Decisão final. Preenche total, minutos, metros e avisos. Devolve o motivo da recusa ou None."""
    c, ref = cfg["criterios"], cfg["referencia"]
    motivo = pre_filtro(a, cfg)
    if motivo:
        return motivo
    if a["quartos"] is None:
        return "quartos não informados"
    a["avisos"] = []
    a["total"] = a["aluguel"] + (a["condominio"] or 0) + (a["iptu"] or 0)
    if a["total"] > c["valor_total_max"]:
        return "total acima do limite"

    ponto_da_rua = geocodificar(a["rua"], "Londrina", estado.setdefault("geocode", {})) if a["rua"] else None
    if a["lat"] is None and ponto_da_rua:
        a["lat"], a["lon"] = ponto_da_rua
    elif ponto_da_rua and distancia_m(ref["lat"], ref["lon"], *ponto_da_rua) > c["raio_busca_m"] + 2500:
        return "a rua fica longe (a coordenada do anúncio está errada)"
    if a["lat"] is None:
        a["minutos"] = a["metros"] = None
        a["avisos"].append("distância não calculada: o anúncio não traz endereço completo")
    else:
        if distancia_m(ref["lat"], ref["lon"], a["lat"], a["lon"]) > c["raio_busca_m"]:
            return "longe"
        a["minutos"], a["metros"] = minutos_a_pe(
            (ref["lat"], ref["lon"]), (a["lat"], a["lon"]), estado.setdefault("rotas", {}))
        if a["minutos"] > c["minutos_a_pe_max"]:
            return "mais de %d min a pé" % c["minutos_a_pe_max"]
        if a["aproximado"]:
            a["avisos"].append("localização aproximada, confira o endereço no anúncio")

    if a["condominio"] is None:
        a["avisos"].append("condomínio não informado, o total pode passar do limite")
    if c["exigir_garagem"] and a["vagas"] is None:
        a["avisos"].append("garagem não informada")
    return None


def chave_endereco(a):
    if not (a.get("rua") and a.get("numero")):
        return None
    return f"{normalizar(a['rua'])}|{a['numero']}|{a['quartos']}|{a['aluguel']:.0f}"


# ---------- execução ----------

CAMPOS_GUARDADOS = ("url", "titulo", "fonte", "anunciante", "rua", "numero", "bairro", "quartos", "vagas",
                    "area", "aluguel", "condominio", "iptu", "total", "minutos", "metros", "elevador",
                    "terreo", "avisos")


def guardar(a):
    """Resumo do anúncio aprovado, para o e-mail com todos os disponíveis."""
    return {k: a.get(k) for k in CAMPOS_GUARDADOS if a.get(k) not in (None, [], "")}


def processar_fonte(fonte, cfg, estado, hoje, orcamento, completa=False):
    """Coleta uma fonte e devolve (novos, base): anúncios aprovados novos e os da primeira leitura.

    completa=True faz a fonte ler todas as páginas, não só as mais recentes.
    """
    modulo = FONTES[fonte["tipo"]]
    registros = estado.setdefault("anuncios", {})
    primeira_vez = fonte["nome"] not in estado.setdefault("fontes_iniciadas", [])
    # fontes com páginas pesadas são lidas com intervalo maior
    leituras = estado.setdefault("ultima_leitura", {})
    intervalo = fonte.get("intervalo_minutos")
    if intervalo and not primeira_vez and time.time() - leituras.get(fonte["nome"], 0) < intervalo * 60 - 90:
        log(f"  {fonte['nome']}: ainda não é hora (lida a cada {intervalo} min)")
        return [], []
    if intervalo:
        leituras[fonte["nome"]] = int(time.time())
    ctx = {"cfg": cfg, "estado": estado, "primeira_vez": primeira_vez, "completa": primeira_vez or completa,
           "log": log}
    brutos = modulo.coletar(fonte, ctx)
    novos, base, pendentes = [], [], 0
    # na primeira leitura de fontes grandes não se abre anúncio por anúncio, para não ser bloqueado
    detalha = hasattr(modulo, "detalhar") and not (primeira_vez and fonte["tipo"] in ("chavesnamao", "santamerica"))

    for a in brutos:
        reg = registros.get(a["chave"])
        mesmo_valor = bool(reg) and reg.get("aluguel") == a["aluguel"]
        # já conhecido e sem mudança: só marca que continua anunciado
        # (aprovados antigos, gravados antes de existir o resumo, passam de novo para guardar os dados)
        if mesmo_valor and not reg.get("tentar_de_novo") and (not reg.get("ok") or "dados" in reg):
            reg["visto"] = hoje
            continue
        motivo = pre_filtro(a, cfg)
        if not motivo and detalha:
            if orcamento[0] <= 0:
                pendentes += 1
                if mesmo_valor:
                    reg["visto"] = hoje  # já conhecido: continua anunciado, só os dados ficam para depois
                continue  # fica para a próxima execução
            orcamento[0] -= 1
            try:
                modulo.detalhar(a, fonte, ctx)
            except Exception as erro:
                tentativas = (reg or {}).get("tentar_de_novo", 0) + 1
                log(f"  detalhe falhou ({a['url']}): {erro}")
                if tentativas < 3:
                    registros[a["chave"]] = {"visto": hoje, "desde": hoje, "tentar_de_novo": tentativas}
                    continue
        if not motivo:
            motivo = avaliar(a, cfg, estado)

        novo_reg = {"visto": hoje, "desde": (reg or {}).get("desde", hoje), "aluguel": a["aluguel"], "ok": not motivo}
        if motivo:
            novo_reg["motivo"] = motivo
        elif mesmo_valor and reg.get("ok"):
            novo_reg["dados"] = guardar(a)  # já tinha sido avisado: só guarda os dados
        else:
            novo_reg["dados"] = guardar(a)
            if reg and reg.get("ok") and reg.get("aluguel"):
                a["mudanca"] = f"Aluguel mudou de {notificar.reais(reg['aluguel'])} para {notificar.reais(a['aluguel'])}"
            ce = chave_endereco(a)
            repetido = estado.setdefault("enderecos", {}).get(ce) if ce else None
            if repetido and repetido["chave"] != a["chave"] and primeira_vez:
                registros[a["chave"]] = novo_reg
                continue  # na lista inicial, o mesmo imóvel aparece uma vez só
            if repetido and repetido["chave"] != a["chave"]:
                a["avisos"].append(
                    f"mesmo endereço e valor de um anúncio de {repetido['data']} ({repetido['anunciante']})")
            elif ce:
                estado["enderecos"][ce] = {"chave": a["chave"], "data": hoje[8:] + "/" + hoje[5:7],
                                           "anunciante": a.get("anunciante") or a["fonte"]}
            (base if primeira_vez else novos).append(a)
        registros[a["chave"]] = novo_reg

    if primeira_vez:
        estado["fontes_iniciadas"].append(fonte["nome"])
    log(f"  {fonte['nome']}: {len(brutos)} anúncios lidos, {len(novos)} novos, "
        f"{len(base)} na lista inicial" + (f", {pendentes} adiados" if pendentes else ""))
    return novos, base


def lista_disponiveis(estado, hoje):
    """Aprovados que apareceram nos sites hoje, sem repetir o mesmo apartamento."""
    vistos, lista = set(), []
    for chave, reg in estado.get("anuncios", {}).items():
        dados = reg.get("dados")
        if not reg.get("ok") or not dados or reg.get("visto") != hoje:
            continue
        a = dict(dados, chave=chave)
        a["avisos"] = [x for x in a.get("avisos", []) if not x.startswith("mesmo endereço")]
        a.setdefault("total", a.get("aluguel"))
        ce = chave_endereco(a) if a.get("aluguel") is not None else None
        if ce in vistos:
            continue
        if ce:
            vistos.add(ce)
        lista.append(a)
    return por_distancia(lista)


def por_distancia(anuncios):
    return sorted(anuncios, key=lambda a: (a.get("minutos") is None, a.get("minutos") or 0))


def enviar(anuncios_novos, base, cfg, canais, sem_enviar):
    """Envia tudo. Devolve True se cada grupo saiu por pelo menos um canal."""
    ref, limites = cfg["referencia"], cfg["limites"]

    def telegram(texto, foto=None):
        if sem_enviar:
            log("\n--- Telegram ---\n" + texto)
            return True
        if not canais["telegram"]:
            return False
        try:
            notificar.enviar_telegram(texto, foto)
            return True
        except Exception as erro:
            log(f"  Telegram falhou: {erro}")
            return False

    def email(assunto, corpo):
        if sem_enviar:
            log("\n--- E-mail ---\n" + assunto)
            return True
        if not canais["email"]:
            return False
        try:
            notificar.enviar_email(assunto, corpo)
            return True
        except Exception as erro:
            log(f"  E-mail falhou: {erro}")
            return False

    tudo_saiu = True
    if base:
        base = por_distancia(base)
        titulo = "Apartamentos disponíveis hoje perto do " + ref["nome"]
        entregas = [telegram(notificar.resumo_telegram(base, ref, titulo)),
                    email(titulo, notificar.resumo_email(base, ref, titulo))]
        tudo_saiu = tudo_saiu and any(entregas)
    if anuncios_novos:
        anuncios_novos = por_distancia(anuncios_novos)
        individuais = anuncios_novos[:limites["alertas_individuais_por_execucao"]]
        resto = anuncios_novos[len(individuais):]
        corpo = "".join(notificar.bloco_email(a, ref) for a in anuncios_novos)
        entregas = [email(notificar.assunto_email(anuncios_novos), corpo)]
        entregas += [telegram(notificar.texto_telegram(a, ref), a.get("imagem")) for a in individuais]
        if resto:
            entregas.append(telegram(notificar.resumo_telegram(resto, ref, "Mais anúncios novos")))
        tudo_saiu = tudo_saiu and any(entregas)
    return tudo_saiu


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--sem-enviar", action="store_true")
    ap.add_argument("--teste", action="store_true")
    ap.add_argument("--gravar", action="store_true", help="com --sem-enviar, grava o estado mesmo assim")
    ap.add_argument("--resumo", action="store_true", help="força o e-mail com todos os disponíveis (depois das 8h)")
    args = ap.parse_args()

    carregar_env()
    cfg = json.loads((RAIZ / "config.json").read_text(encoding="utf-8"))
    canais = notificar.canais()
    agora = datetime.now(BRASILIA)
    hoje = agora.strftime("%Y-%m-%d")

    if args.teste:
        texto = "Teste do alerta de imóveis: se você recebeu esta mensagem, o envio está funcionando."
        if canais["telegram"]:
            notificar.enviar_telegram(texto)
            log("Telegram: enviado")
        else:
            log("Telegram: não configurado")
        if canais["email"]:
            notificar.enviar_email("Teste do alerta de imóveis", f"<p>{texto}</p>")
            log("E-mail: enviado")
        else:
            log("E-mail: não configurado")
        return 0

    if not args.sem_enviar and not any(canais.values()):
        log("Nenhum canal de envio configurado (Telegram ou e-mail). Use --sem-enviar para testar.")
        return 2

    estado = carregar_estado()
    falhas = estado.setdefault("falhas", {})
    limites = cfg["limites"]
    orcamento = [limites["detalhes_por_execucao"]]
    novos, base, avisos_fonte = [], [], []
    log(f"Verificação de {agora:%d/%m/%Y %H:%M}")

    # e-mail com todos os disponíveis: no dia dele, todas as fontes leem todas as páginas
    cfg_resumo = cfg.get("resumo_disponiveis") or {}
    resumo_devido = False
    if cfg_resumo.get("a_cada_dias") and agora.hour >= cfg_resumo.get("hora", 8):
        if not estado.get("ultimo_resumo_disponiveis"):
            # primeira vez: espera um dia, para dar tempo de guardar os dados dos anúncios já conhecidos
            estado["ultimo_resumo_disponiveis"] = (agora - timedelta(days=cfg_resumo["a_cada_dias"] - 1)).strftime("%Y-%m-%d")
        ultimo = estado["ultimo_resumo_disponiveis"]
        dias = (agora.date() - datetime.strptime(ultimo, "%Y-%m-%d").date()).days
        resumo_devido = dias >= cfg_resumo["a_cada_dias"] or args.resumo
    if resumo_devido:
        log("  (leitura completa para o e-mail com todos os disponíveis)")

    for fonte in cfg["fontes"]:
        nome = fonte["nome"]
        if fonte.get("ativa") is False:
            falhas.pop(nome, None)
            continue
        try:
            n, b = processar_fonte(fonte, cfg, estado, hoje, orcamento, completa=resumo_devido)
            novos += n
            base += b
            if falhas.get(nome, 0) >= limites["falhas_seguidas_para_avisar"]:
                avisos_fonte.append(f"A fonte {nome} voltou a funcionar.")
            falhas.pop(nome, None)
        except Exception as erro:
            falhas[nome] = falhas.get(nome, 0) + 1
            log(f"  {nome}: FALHOU ({erro})")
            if os.environ.get("DEPURAR"):
                traceback.print_exc()
            if falhas[nome] == limites["falhas_seguidas_para_avisar"]:
                avisos_fonte.append(f"A fonte {nome} falhou {falhas[nome]} vezes seguidas. Último erro: {erro}")

    # esquece anúncios que não aparecem há muito tempo
    corte = (agora - timedelta(days=limites["dias_para_esquecer"])).strftime("%Y-%m-%d")
    estado["anuncios"] = {k: v for k, v in estado.get("anuncios", {}).items() if v.get("visto", hoje) >= corte}
    vivos = {v_chave for v_chave in estado["anuncios"]}
    estado["enderecos"] = {k: v for k, v in estado.get("enderecos", {}).items() if v["chave"] in vivos}

    entregue = enviar(novos, base, cfg, canais, args.sem_enviar)

    if resumo_devido:
        disponiveis = lista_disponiveis(estado, hoje)
        titulo = f"Apartamentos disponíveis perto do {cfg['referencia']['nome']} · {agora:%d/%m}"
        intro = (f"{len(disponiveis)} apartamentos dentro do perfil continuam anunciados hoje, do mais perto "
                 f"para o mais longe. Este e-mail chega a cada {cfg_resumo['a_cada_dias']} dias; os anúncios "
                 "novos continuam chegando na hora, separados.")
        if args.sem_enviar:
            log(f"\n=== E-MAIL COM TODOS OS DISPONÍVEIS ({len(disponiveis)}) ===")
            for a in disponiveis:
                log(f"{notificar.linha_resumo(a, cfg['referencia'])} · {notificar.origem(a)}")
        elif disponiveis and canais["email"]:
            try:
                notificar.enviar_email(titulo, notificar.resumo_email(disponiveis, cfg["referencia"], titulo, intro))
                estado["ultimo_resumo_disponiveis"] = hoje
            except Exception as erro:
                log(f"  E-mail com todos os disponíveis falhou: {erro}")
        else:
            estado["ultimo_resumo_disponiveis"] = hoje

    if args.sem_enviar:
        for titulo, grupo in (("NOVOS", novos), ("LISTA INICIAL", base)):
            if grupo:
                log(f"\n=== {titulo} ({len(grupo)}) ===")
            for a in por_distancia(grupo):
                log(f"{notificar.linha_resumo(a, cfg['referencia'])} · {notificar.acesso(a)} · "
                    f"{notificar.origem(a)}" + "".join(f" · ATENÇÃO: {x}" for x in a["avisos"]))
        if args.gravar:
            salvar_estado(estado)
        log(f"\nResultado: {len(novos)} novos, {len(base)} na lista inicial. Nada foi enviado"
            + ("." if args.gravar else " nem gravado."))
        return 0

    if not entregue:
        # nada saiu: esquece estes anúncios para tentar de novo na próxima execução
        for a in novos + base:
            estado["anuncios"].pop(a["chave"], None)
        if base:
            nomes = {a["fonte"] for a in base}
            estado["fontes_iniciadas"] = [f for f in estado["fontes_iniciadas"] if f not in nomes]

    def avisar(texto):
        if canais["telegram"]:
            notificar.enviar_telegram(texto)
        else:
            notificar.enviar_email("Monitor de imóveis", f"<p>{texto}</p>")

    try:
        for aviso in avisos_fonte:
            avisar(aviso)
        contagem = estado.setdefault("alertas_por_dia", {})
        if novos and entregue:
            contagem[hoje] = contagem.get(hoje, 0) + len(novos)
        if agora.hour >= cfg["resumo_diario_hora"] and estado.get("ultimo_status") != hoje:
            ontem = (agora - timedelta(days=1)).strftime("%Y-%m-%d")
            if estado.get("ultimo_status"):  # no primeiro dia a lista inicial já serve de sinal de vida
                avisar(f"Monitor de imóveis funcionando. Alertas enviados ontem: {contagem.get(ontem, 0)}. "
                       f"Fontes com erro agora: {', '.join(sorted(falhas)) or 'nenhuma'}.")
            estado["ultimo_status"] = hoje
            estado["alertas_por_dia"] = {d: n for d, n in contagem.items() if d >= ontem}
    except Exception as erro:
        log(f"  aviso de situação falhou: {erro}")

    salvar_estado(estado)
    log(f"Resultado: {len(novos)} novos, {len(base)} na lista inicial, entrega {'ok' if entregue else 'FALHOU'}.")
    return 0 if entregue else 1


if __name__ == "__main__":
    sys.exit(main())
