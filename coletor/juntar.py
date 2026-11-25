#!/usr/bin/env python3
"""Junta a base histórica (um diretório por mês) e o legado num só resumo para a plataforma: aprendizados.json.
Uso: python juntar.py --base ../base --saida ../base/aprendizados.json"""
import argparse, glob, json, os, sys, tempfile, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ler_atas as LA  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--base", required=True)
ap.add_argument("--saida", required=True)
a = ap.parse_args()
tmp = tempfile.mkdtemp()
pastas = sorted(glob.glob(os.path.join(a.base, "20??-??"))) + [os.path.join(a.base, "legado")]
tipos = collections.Counter(); docs = collections.Counter(); meses = {}
with open(os.path.join(tmp, "casos.jsonl"), "w") as fc, open(os.path.join(tmp, "participantes.jsonl"), "w") as fp, open(os.path.join(tmp, "processados.txt"), "w") as fpr:
    for p in pastas:
        for nome, f in (("casos.jsonl", fc), ("participantes.jsonl", fp)):
            q = os.path.join(p, nome)
            if os.path.exists(q):
                f.write(open(q, encoding="utf-8").read())
        if os.path.exists(os.path.join(p, "processados.txt")):
            fpr.write(open(os.path.join(p, "processados.txt")).read())
        ind = os.path.join(p, "indice.jsonl")
        if os.path.exists(ind):
            for l in open(ind, encoding="utf-8"):
                if l.strip():
                    r = json.loads(l); fpr.write(r["id"] + "\n")
                    for t in r.get("tipos") or []:
                        tipos[t] += 1
        dq = os.path.join(p, "documentos.jsonl")
        if os.path.exists(dq):
            for l in open(dq, encoding="utf-8"):
                if l.strip():
                    docs[json.loads(l).get("tipo")] += 1
        e = os.path.join(p, "estatisticas.json")
        if os.path.exists(e):
            meses[os.path.basename(p)] = json.load(open(e))
LA.gerar_resumo(tmp, a.saida)
r = json.load(open(a.saida))
r["base_historica"] = {"meses": {k: {x: v.get(x) for x in ("licitacoes_no_mes", "verificadas", "casos", "documentos", "completo")} for k, v in meses.items()},
                       "licitacoes_com_documento": dict(tipos), "documentos_guardados": dict(docs)}
json.dump(r, open(a.saida, "w"), ensure_ascii=False, separators=(",", ":"))
print("ok", r["total_casos"], "casos;", sum(docs.values()), "documentos de impugnação/recurso/esclarecimento", file=sys.stderr)
