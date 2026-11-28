#!/usr/bin/env python3
"""Junta a base de mercado (um arquivo por mês) num resumo compacto para a página "Relatório de mercado".

Entradas:
  --mercado  pasta com <AAAA-MM>.jsonl.gz (saída de mercado.py)
  --base     pasta do ramo base (opcional): <AAAA-MM>/participantes.jsonl e casos.jsonl, para concorrência e inabilitações

Saída (--saida, JSON):
  dims   listas de meses, subsegmentos ("Segmento|Subsegmento"), UFs e modalidades (as linhas usam os índices)
  serie  [mês, sub, uf, licitações, soma do valor estimado, nº com valor estimado, soma homologada, nº com homologado]
  chaves por "sub|uf" (e "sub|BR"), só dos últimos 24 meses:
    org  maiores compradores [nome, cnpj, município, licitações, valor estimado]
    mun  municípios [nome, licitações, valor]
    mod  licitações por modalidade {índice: n}
    srp  quantas são registro de preços
    conc concorrência [licitações com ata lida, participações, nº de casos de inabilitação/desclassificação]
    forn fornecedores que mais disputam [nome, cnpj, participações]
    mot  principais motivos de inabilitação [categoria, n]
"""
import argparse
import collections
import datetime as dt
import glob
import gzip
import json
import os

C = collections.Counter
D = collections.defaultdict


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mercado", required=True)
    ap.add_argument("--base", default="")
    ap.add_argument("--saida", required=True)
    ap.add_argument("--janela", type=int, default=24, help="meses usados nos rankings")
    a = ap.parse_args()

    arquivos = sorted(glob.glob(os.path.join(a.mercado, "*.jsonl.gz")))
    meses = [os.path.basename(f)[:7] for f in arquivos]
    hoje = dt.date.today()
    corte = (hoje.replace(day=1) - dt.timedelta(days=31 * a.janela)).strftime("%Y-%m")
    subs, ufs, mods = {}, {}, {}
    idx = lambda d, k: d.setdefault(k, len(d))

    serie = D(lambda: [0, 0.0, 0, 0.0, 0])
    org = D(lambda: D(lambda: [0, 0.0, ""]))
    mun = D(lambda: D(lambda: [0, 0.0]))
    mod = D(C)
    srp = C()
    sub_de = {}  # id da licitação -> (sub, uf), para cruzar com participantes/casos
    nomes_org = {}

    for f, mes in zip(arquivos, meses):
        recente = mes >= corte
        with gzip.open(f, "rt", encoding="utf-8", errors="replace") as fh:
            for l in fh:
                try:
                    r = json.loads(l)
                except json.JSONDecodeError:
                    continue
                s = idx(subs, f"{r.get('seg') or 'Outros'}|{r.get('sub') or ''}")
                u = idx(ufs, r.get("uf") or "??")
                pm = (r.get("pub") or mes)[:7]
                if pm not in meses:
                    pm = mes
                m = meses.index(pm)
                v, h = r.get("vest") or 0, r.get("vhom") or 0
                # valores absurdos (erro de digitação do órgão) distorcem médias: acima de R$ 5 bi não entra na soma
                if v > 5e9:
                    v = 0
                if h > 5e9:
                    h = 0
                x = serie[(m, s, u)]
                x[0] += 1
                if v:
                    x[1] += v; x[2] += 1
                if h:
                    x[3] += h; x[4] += 1
                if not recente:
                    continue
                sub_de[r["id"]] = (s, u)
                for k in (f"{s}|{u}", f"{s}|BR"):
                    oc = r.get("ocnpj") or r.get("org") or "?"
                    o = org[k][oc]; o[0] += 1; o[1] += v; o[2] = r.get("mun") or ""
                    nomes_org[oc] = r.get("org") or ""
                    if k.endswith("|BR"):
                        mm = mun[k][f"{r.get('mun') or '?'}/{r.get('uf') or ''}"]
                    else:
                        mm = mun[k][r.get("mun") or "?"]
                    mm[0] += 1; mm[1] += v
                    mod[k][idx(mods, r.get("mod") or "?")] += 1
                    if r.get("srp"):
                        srp[k] += 1
        print(mes, len(serie), "células", flush=True)

    conc = D(lambda: [set(), 0, 0])
    forn = D(lambda: D(lambda: [0, ""]))
    mot = D(C)
    if a.base:
        for p in sorted(glob.glob(os.path.join(a.base, "*", "participantes.jsonl"))):
            for l in open(p, encoding="utf-8", errors="replace"):
                try:
                    r = json.loads(l)
                except json.JSONDecodeError:
                    continue
                su = sub_de.get(r.get("lic"))
                if not su:
                    continue
                for k in (f"{su[0]}|{su[1]}", f"{su[0]}|BR"):
                    c = conc[k]; c[0].add(r["lic"]); c[1] += 1
                    cn = r.get("cnpj") or r.get("nome")
                    if cn:
                        fo = forn[k][cn]; fo[0] += 1; fo[1] = fo[1] or (r.get("nome") or "").strip(" (")
        for p in sorted(glob.glob(os.path.join(a.base, "*", "casos.jsonl"))):
            for l in open(p, encoding="utf-8", errors="replace"):
                try:
                    r = json.loads(l)
                except json.JSONDecodeError:
                    continue
                su = sub_de.get(r.get("lic"))
                if not su:
                    continue
                for k in (f"{su[0]}|{su[1]}", f"{su[0]}|BR"):
                    conc[k][0].add(r["lic"]); conc[k][2] += 1
                    mot[k][r.get("categoria") or "Outros motivos"] += 1

    chaves = {}
    for k in set(org) | set(conc):
        tot = sum(o[0] for o in org[k].values())
        if tot < 5 and not k.endswith("|BR"):
            continue
        e = {}
        e["org"] = [[nomes_org.get(c, c)[:90], c if c and c.isdigit() else "", o[2], o[0], round(o[1])]
                    for c, o in sorted(org[k].items(), key=lambda t: (-t[1][0], -t[1][1]))[:10]]
        e["mun"] = [[n[:60], m[0], round(m[1])] for n, m in sorted(mun[k].items(), key=lambda t: -t[1][0])[:8]]
        e["mod"] = dict(mod[k])
        e["srp"] = srp[k]
        if k in conc:
            c = conc[k]
            e["conc"] = [len(c[0]), c[1], c[2]]
            e["forn"] = [[f[1][:80], cn if cn.isdigit() else "", f[0]] for cn, f in sorted(forn[k].items(), key=lambda t: -t[1][0])[:10]]
            e["mot"] = mot[k].most_common(6)
        chaves[k] = e

    inv = lambda d: [k for k, _ in sorted(d.items(), key=lambda t: t[1])]
    out = {
        "gerado_em": dt.datetime.now().isoformat(timespec="seconds"),
        "janela_meses": a.janela, "corte_rankings": corte,
        "dims": {"meses": meses, "subs": inv(subs), "ufs": inv(ufs), "mods": inv(mods)},
        "serie": [[m, s, u, x[0], round(x[1]), x[2], round(x[3]), x[4]] for (m, s, u), x in sorted(serie.items())],
        "chaves": chaves,
    }
    json.dump(out, open(a.saida, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print("ok", a.saida, os.path.getsize(a.saida) // 1024, "KB,", len(out["serie"]), "linhas,", len(chaves), "chaves")


if __name__ == "__main__":
    main()
