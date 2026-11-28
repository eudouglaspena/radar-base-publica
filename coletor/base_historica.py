#!/usr/bin/env python3
"""Base histórica (desde a Lei 14.133): percorre UM MÊS de pregões e concorrências publicados no PNCP
e lê os documentos que contam o que aconteceu na disputa.

Para cada licitação:
  1. lista os arquivos no PNCP (uma chamada leve);
  2. se houver ata, julgamento, parecer de habilitação, recurso, decisão, impugnação ou esclarecimento,
     baixa esses arquivos e lê o texto;
  3. das atas, julgamentos e recursos extrai inabilitações e desclassificações com o motivo (mesmas regras de ler_atas.py)
     e os participantes;
  4. de impugnações, esclarecimentos, recursos e decisões guarda um trecho do texto (para a extração por IA depois).

Saída em <saida>/<AAAA-MM>/:
  indice.jsonl        uma linha por licitação verificada: id e tipos de documento encontrados
  casos.jsonl         inabilitações/desclassificações (mesmo formato de atas/casos.jsonl)
  participantes.jsonl participações (licitação × empresa)
  documentos.jsonl    impugnações, esclarecimentos, recursos e decisões: metadados + trecho do texto
  estatisticas.json   contagens do mês

Uso:  python base_historica.py --mes 2025-03 --saida ../base --threads 12
"""
import argparse
import concurrent.futures as cf
import datetime as dt
import json
import os
import re
import sys
import threading
import time
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ler_atas as LA  # noqa: E402
from segmentos import classificar_completo  # noqa: E402

CONSULTA = "https://pncp.gov.br/api/consulta/v1/contratacoes/publicacao"
MODALIDADES = (6, 4, 7, 5)  # pregão eletrônico, concorrência eletrônica, pregão presencial, concorrência presencial

TIPOS = [  # (tipo, regex no título/tipo do documento) — a ordem importa
    ("impugnacao", re.compile(r"impugna", re.I)),
    ("esclarecimento", re.compile(r"esclarec|pedido de informa|questionamento", re.I)),
    ("recurso", re.compile(r"recurso|contrarraz|contra-raz", re.I)),
    ("decisao", re.compile(r"decis[aã]o|parecer jur", re.I)),
    ("julgamento", re.compile(r"julgament|habilita|inabilita|parecer t[eé]cn|an[aá]lise (de |da |dos )?(document|proposta|habilit)|relat[oó]rio (de|do) (julgamento|agente|pregoeiro|comiss)", re.I)),
    ("ata", re.compile(r"\bata\b|ata[_ -](de[_ -])?(sess|julg|abert|preg|concorr|reuni)|sess[aã]o p[uú]blica|atatotal|lances", re.I)),
    ("retificacao", re.compile(r"retifica|errata|aditamento|edital (corrigido|alterado|republicad)", re.I)),
]
IGNORAR = re.compile(r"registro de pre[cç]o|\barp\b|minuta|termo de refer|estudo t[eé]cnico|\betp\b|projeto|planilha|or[cç]amento|memorial|cronograma|\bbdi\b|mapa de risco", re.I)
LER = {"ata", "julgamento", "recurso", "decisao", "impugnacao", "esclarecimento"}
COM_CASOS = {"ata", "julgamento", "recurso", "decisao"}
GUARDAR_TEXTO = {"impugnacao", "esclarecimento", "recurso", "decisao"}
TRECHO = 6000

trava = threading.Lock()


def jget(url):
    corpo = LA.get(url, tentativas=4, timeout=90)
    try:
        return json.loads(corpo) if corpo else None
    except json.JSONDecodeError:
        return None


def listar_mes(mes):
    ini = dt.date.fromisoformat(mes + "-01")
    fim = (ini.replace(day=28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1)
    tarefas = []
    d = ini
    while d <= fim:
        for m in MODALIDADES:
            tarefas.append((d, m))
        d += dt.timedelta(days=1)

    falhas = []

    def pagina(d, m, pag):
        url = CONSULTA + "?" + urllib.parse.urlencode({"dataInicial": d.strftime("%Y%m%d"), "dataFinal": d.strftime("%Y%m%d"),
                                                       "codigoModalidadeContratacao": m, "pagina": pag, "tamanhoPagina": 50})
        for i in range(6):
            corpo = LA.get(url, tentativas=1, timeout=120)
            if corpo is not None:
                if not corpo.strip():
                    return {}  # 204: dia sem licitações
                try:
                    return json.loads(corpo)
                except json.JSONDecodeError:
                    pass
            time.sleep(3 * (i + 1))
        falhas.append(f"{d} mod {m} pág {pag}")
        return None

    def um_dia(t):
        d, m = t
        out, pag = [], 1
        while True:
            j = pagina(d, m, pag)
            if j is None:
                return out
            for c in j.get("data") or []:
                uo = c.get("unidadeOrgao") or {}; oe = c.get("orgaoEntidade") or {}
                if not c.get("numeroControlePNCP"):
                    continue
                out.append({"id": c["numeroControlePNCP"], "cnpj": oe.get("cnpj"), "ano": c.get("anoCompra"), "seq": c.get("sequencialCompra"),
                            "uf": uo.get("ufSigla"), "mun": uo.get("municipioNome"), "mod": c.get("modalidadeNome"),
                            "obj": " ".join((c.get("objetoCompra") or "").split())[:300], "org": oe.get("razaoSocial"),
                            "enc": c.get("dataEncerramentoProposta"), "vest": c.get("valorTotalEstimado"), "vhom": c.get("valorTotalHomologado"),
                            "sit": c.get("situacaoCompraNome"), "pub": (c.get("dataPublicacaoPncp") or "")[:10], "srp": c.get("srp")})
            if not j.get("data") or pag >= (j.get("totalPaginas") or 1):
                return out
            pag += 1

    lic = {}
    with cf.ThreadPoolExecutor(4) as ex:
        for lista in ex.map(um_dia, tarefas):
            for r in lista:
                lic[r["id"]] = r
    if falhas:
        print(f"  ATENÇÃO: {len(falhas)} páginas da listagem falharam, ex.: {falhas[:5]}", file=sys.stderr)
    return list(lic.values()), falhas


def tipo_doc(d):
    tit = f"{d.get('titulo') or ''} | {d.get('tipoDocumentoNome') or ''}"
    for t, rx in TIPOS:
        if rx.search(tit):
            if t in ("ata", "julgamento") and IGNORAR.search(d.get("titulo") or ""):
                return None
            return t
    return None


def processar(r, arqs):
    """Devolve (indice, casos, participantes, documentos) de uma licitação."""
    docs = jget(f"{LA.API}/orgaos/{r['cnpj']}/compras/{r['ano']}/{r['seq']}/arquivos") or []
    achados = []
    for d in docs:
        if d.get("statusAtivo") is False:
            continue
        t = tipo_doc(d)
        if t:
            achados.append((t, d))
    ind = {"id": r["id"], "n": len(docs), "tipos": sorted(set(t for t, _ in achados))}
    casos, parts, guard = [], [], []
    if not achados:
        return ind, casos, parts, guard
    seg, sub, nat = classificar_completo(r.get("obj") or "")
    base = {"lic": r["id"], "uf": r.get("uf"), "mun": r.get("mun"), "seg": seg, "sub": sub, "mod": r.get("mod"), "obj": (r.get("obj") or "")[:160],
            "org": r.get("org"), "enc": (r.get("enc") or "")[:10], "vest": r.get("vest")}
    lidos = 0
    for t, d in achados[-6:]:
        if t not in LER or lidos >= 5:
            continue
        cont = LA.get(d.get("url") or "", tentativas=2, timeout=120)
        if not cont or len(cont) > 30_000_000:
            continue
        txt = LA.textos_pdf(cont, max_paginas=80)
        if len(txt) < 150:
            continue
        lidos += 1
        if t in COM_CASOS:
            eventos, ps = LA.extrair(txt)
            for e in eventos:
                if e["cnpj"] and not e["empresa"]:
                    e["empresa"] = ps.get(e["cnpj"]) or None
                casos.append({**base, **e, "fonte": t, "ata": d.get("url"), "ata_titulo": (d.get("titulo") or "")[:80]})
            for c, nome in ps.items():
                if c != r.get("cnpj"):
                    parts.append({"lic": r["id"], "uf": r.get("uf"), "seg": seg, "cnpj": c, "nome": nome, "enc": base["enc"]})
        if t in GUARDAR_TEXTO:
            plano = re.sub(r"[ \t]+", " ", txt)
            plano = re.sub(r"\n{3,}", "\n\n", plano).strip()
            guard.append({**base, "tipo": t, "titulo": (d.get("titulo") or "")[:120], "url": d.get("url"), "chars": len(plano), "texto": plano[:TRECHO]})
    return ind, casos, parts, guard


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mes", required=True, help="AAAA-MM")
    ap.add_argument("--saida", default=os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "base")))
    ap.add_argument("--threads", type=int, default=12)
    ap.add_argument("--limite-min", type=int, default=330, help="para com folga antes do limite do GitHub (min)")
    a = ap.parse_args()
    t0 = time.time()
    pasta = os.path.join(a.saida, a.mes)
    os.makedirs(pasta, exist_ok=True)
    fi = os.path.join(pasta, "indice.jsonl")
    feitos = set()
    if os.path.exists(fi):
        feitos = {json.loads(l)["id"] for l in open(fi, encoding="utf-8") if l.strip()}
    lic, falhas = listar_mes(a.mes)
    alvo = [r for r in lic if r["id"] not in feitos and r.get("cnpj") and r.get("ano") and r.get("seq")]
    print(f"{a.mes}: {len(lic)} licitações no mês, {len(alvo)} a verificar ({len(feitos)} já feitas) · listagem em {time.time()-t0:.0f}s", file=sys.stderr)
    # errors="replace": PDFs mal formados às vezes trazem caracteres inválidos; não podem derrubar o mês inteiro
    arq = {k: open(os.path.join(pasta, k + ".jsonl"), "a", encoding="utf-8", errors="replace") for k in ("indice", "casos", "participantes", "documentos")}
    n = {"verificadas": 0, "com_documentos": 0, "casos": 0, "participacoes": 0, "documentos": 0}
    tipos = {}
    parou = False
    with cf.ThreadPoolExecutor(a.threads) as ex:
        futs = {ex.submit(processar, r, None): r for r in alvo}
        for f in cf.as_completed(futs):
            if f.cancelled():
                continue
            try:
                ind, casos, parts, guard = f.result()
            except Exception as e:  # noqa: BLE001
                print("erro", futs[f]["id"], repr(e), file=sys.stderr)
                continue
            with trava:
                arq["indice"].write(json.dumps(ind, ensure_ascii=False) + "\n")
                for c in casos:
                    arq["casos"].write(json.dumps(c, ensure_ascii=False) + "\n")
                for p in parts:
                    arq["participantes"].write(json.dumps(p, ensure_ascii=False) + "\n")
                for g in guard:
                    arq["documentos"].write(json.dumps(g, ensure_ascii=False) + "\n")
                n["verificadas"] += 1; n["com_documentos"] += bool(ind["tipos"]); n["casos"] += len(casos)
                n["participacoes"] += len(parts); n["documentos"] += len(guard)
                for t in ind["tipos"]:
                    tipos[t] = tipos.get(t, 0) + 1
                if n["verificadas"] % 500 == 0:
                    for x in arq.values():
                        x.flush()
                    print(f"  {n['verificadas']}/{len(alvo)} · {n['casos']} casos · {n['documentos']} docs · {(time.time()-t0)/60:.0f} min", file=sys.stderr)
            if (time.time() - t0) / 60 > a.limite_min and not parou:
                parou = True
                print("  limite de tempo: parando; o resto fica para a próxima execução", file=sys.stderr)
                for x in futs:
                    x.cancel()
    for x in arq.values():
        x.close()
    est = {"mes": a.mes, "licitacoes_no_mes": len(lic), "completo": not parou, "tipos": tipos, **n, "minutos": round((time.time() - t0) / 60, 1)}
    ant = os.path.join(pasta, "estatisticas.json")
    if os.path.exists(ant):
        o = json.load(open(ant))
        for k in ("verificadas", "com_documentos", "casos", "participacoes", "documentos"):
            est[k] += o.get(k, 0)
        for k, v in (o.get("tipos") or {}).items():
            est["tipos"][k] = est["tipos"].get(k, 0) + v
        est["minutos"] += o.get("minutos", 0)
    est["completo"] = (len(feitos) + n["verificadas"] >= len(lic) - 5) and not falhas
    est["falhas_listagem"] = len(falhas)
    json.dump(est, open(ant, "w"), ensure_ascii=False, indent=1)
    print(json.dumps(est, ensure_ascii=False), file=sys.stderr)


if __name__ == "__main__":
    main()
