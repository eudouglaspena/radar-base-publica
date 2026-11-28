#!/usr/bin/env python3
"""Contratos publicados no PNCP em um mês: quem ganhou, por quanto, de qual órgão.

Usa a consulta pública /v1/contratos (por data de publicação). Cada contrato traz o fornecedor (CNPJ e nome),
o valor e o número da compra de origem (numeroControlePncpCompra), que liga o contrato à licitação da base de mercado.

Saída: <saida>/contratos-<AAAA-MM>.jsonl.gz e contratos-<AAAA-MM>.json (estatísticas)
Uso:  python contratos.py --mes 2025-03 --saida ../mercado/meses
"""
import argparse
import concurrent.futures as cf
import datetime as dt
import gzip
import json
import os
import re
import sys
import time
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ler_atas as LA  # noqa: E402
from segmentos import classificar_completo  # noqa: E402

URL = "https://pncp.gov.br/api/consulta/v1/contratos"
IGNORAR_TIPO = re.compile(r"aditivo|apostil|rescis", re.I)


def listar(mes):
    ini = dt.date.fromisoformat(mes + "-01")
    fim = (ini.replace(day=28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1)
    dias = [ini + dt.timedelta(days=i) for i in range((fim - ini).days + 1)]
    falhas = []

    def pagina(d, pag, tam):
        url = URL + "?" + urllib.parse.urlencode({"dataInicial": d.strftime("%Y%m%d"), "dataFinal": d.strftime("%Y%m%d"), "pagina": pag, "tamanhoPagina": tam})
        for i in range(6):
            corpo = LA.get(url, tentativas=1, timeout=150)
            if corpo is not None:
                if not corpo.strip():
                    return {}
                try:
                    j = json.loads(corpo)
                    if isinstance(j, dict) and j.get("status") == "400":
                        return None
                    return j
                except json.JSONDecodeError:
                    pass
            time.sleep(3 * (i + 1))
        return None

    def um_dia(d):
        out, pag, tam = [], 1, 500
        while True:
            j = pagina(d, pag, tam)
            if j is None and tam == 500:  # alguns dias o servidor recusa páginas grandes
                tam, pag, out = 100, 1, []
                continue
            if j is None:
                falhas.append(f"{d} pág {pag}")
                return out
            for c in j.get("data") or []:
                tipo = ((c.get("tipoContrato") or {}).get("nome")) or ""
                if IGNORAR_TIPO.search(tipo):
                    continue
                oe, uo = c.get("orgaoEntidade") or {}, c.get("unidadeOrgao") or {}
                v = c.get("valorGlobal") or c.get("valorInicial")
                try:
                    v = round(float(v), 2)
                except (TypeError, ValueError):
                    v = None
                obj = " ".join((c.get("objetoContrato") or "").split())
                out.append({"id": c.get("numeroControlePNCP"), "compra": c.get("numeroControlePncpCompra"),
                            "fcnpj": c.get("niFornecedor"), "fnome": (c.get("nomeRazaoSocialFornecedor") or "").strip()[:120],
                            "valor": v, "ass": c.get("dataAssinatura"), "pub": (c.get("dataPublicacaoPncp") or "")[:10],
                            "uf": uo.get("ufSigla"), "mun": uo.get("municipioNome"), "org": oe.get("razaoSocial"), "ocnpj": oe.get("cnpj"),
                            "cat": (c.get("categoriaProcesso") or {}).get("nome"), "tipo": tipo, "obj": obj[:300]})
            if not j.get("data") or pag >= (j.get("totalPaginas") or 1):
                return out
            pag += 1

    todos = {}
    with cf.ThreadPoolExecutor(4) as ex:
        for lista in ex.map(um_dia, dias):
            for r in lista:
                if r["id"]:
                    todos[r["id"]] = r
    return list(todos.values()), falhas


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mes", required=True)
    ap.add_argument("--saida", required=True)
    a = ap.parse_args()
    t0 = time.time()
    os.makedirs(a.saida, exist_ok=True)
    lst, falhas = listar(a.mes)
    with gzip.open(os.path.join(a.saida, f"contratos-{a.mes}.jsonl.gz"), "wt", encoding="utf-8", errors="replace") as f:
        for r in lst:
            r["seg"], r["sub"], r["nat"] = classificar_completo(r["obj"])
            r["obj"] = r["obj"][:180]
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    est = {"mes": a.mes, "contratos": len(lst), "falhas_listagem": len(falhas), "completo": not falhas, "minutos": round((time.time() - t0) / 60, 1)}
    json.dump(est, open(os.path.join(a.saida, f"contratos-{a.mes}.json"), "w"), ensure_ascii=False)
    print(json.dumps(est, ensure_ascii=False), file=sys.stderr)


if __name__ == "__main__":
    main()
