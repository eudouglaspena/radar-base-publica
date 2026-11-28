#!/usr/bin/env python3
"""Base de mercado: lista TODOS os pregões e concorrências publicados no PNCP em um mês, com valor,
órgão, município, modalidade e situação, e classifica cada um por segmento/subsegmento/natureza.

Não baixa documentos (só a listagem), então é leve. Serve para o "Relatório de mercado" da plataforma:
quantas licitações saem por mês num segmento, quanto valem, quem compra, onde e como.

Saída: <saida>/<AAAA-MM>.jsonl.gz (uma linha por licitação) e <saida>/<AAAA-MM>.json (estatísticas do mês)

Uso:  python mercado.py --mes 2025-03 --saida ../mercado
"""
import argparse
import gzip
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from base_historica import listar_mes  # noqa: E402
from segmentos import classificar_completo  # noqa: E402


def num(v):
    try:
        v = float(v)
        return round(v, 2) if v > 0 else None
    except (TypeError, ValueError):
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mes", required=True)
    ap.add_argument("--saida", required=True)
    a = ap.parse_args()
    t0 = time.time()
    os.makedirs(a.saida, exist_ok=True)
    lic, falhas = listar_mes(a.mes)
    with gzip.open(os.path.join(a.saida, a.mes + ".jsonl.gz"), "wt", encoding="utf-8", errors="replace") as f:
        for r in lic:
            seg, sub, nat = classificar_completo(r.get("obj") or "")
            f.write(json.dumps({
                "id": r["id"], "pub": r.get("pub") or a.mes + "-15", "uf": r.get("uf"), "mun": r.get("mun"),
                "org": r.get("org"), "ocnpj": r.get("cnpj"), "mod": r.get("mod"), "sit": r.get("sit"),
                "vest": num(r.get("vest")), "vhom": num(r.get("vhom")), "srp": bool(r.get("srp")),
                "seg": seg, "sub": sub, "nat": nat, "obj": (r.get("obj") or "")[:220],
            }, ensure_ascii=False) + "\n")
    est = {"mes": a.mes, "licitacoes": len(lic), "falhas_listagem": len(falhas), "completo": not falhas,
           "minutos": round((time.time() - t0) / 60, 1)}
    json.dump(est, open(os.path.join(a.saida, a.mes + ".json"), "w"), ensure_ascii=False)
    print(json.dumps(est, ensure_ascii=False), file=sys.stderr)


if __name__ == "__main__":
    main()
