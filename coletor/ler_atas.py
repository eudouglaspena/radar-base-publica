#!/usr/bin/env python3
"""Lê as atas das licitações encerradas (publicadas no PNCP) e extrai:
  - participantes (CNPJ e razão social),
  - inabilitações e desclassificações, com o motivo escrito pelo pregoeiro,
  - a categoria do motivo (regras abaixo).

Acumula tudo em uma pasta (por padrão ../atas):
  casos.jsonl          um caso de inabilitação/desclassificação por linha
  participantes.jsonl  uma participação (licitação × empresa) por linha
  processados.txt      ids de licitações já verificadas
E gera um resumo para a página: aprendizados.json

Uso:
  python ler_atas.py --dados ../data/licitacoes.json --max 300
"""
import argparse
import collections
import datetime as dt
import io
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import zipfile

try:
    from pypdf import PdfReader
except ImportError:
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "--user", "--quiet", "pypdf"], check=False)
    from pypdf import PdfReader

API = "https://pncp.gov.br/api/pncp/v1"
AQUI = os.path.dirname(os.path.abspath(__file__))
MODS_COMPETITIVAS = re.compile(r"preg|concorr", re.I)
ATA_TITULO = re.compile(r"\bata\b|ata[_ -]|julgamento|adjudica|habilita|lances|propostas do processo|vencedores|relat[oó]rio|resultado|fracassad|deserta", re.I)
NAO_ATA = re.compile(r"registro de pre[cç]o|minuta|edital|termo de refer|anexo", re.I)
CNPJ = re.compile(r"\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}")

# ----- categorias de motivo (ordem importa) -----
CATEGORIAS = [
    ("Desistência do próprio licitante", r"a pedido d[oa] (licitante|empresa|fornecedor)|solicitou (o )?cancelamento|desist"),
    ("Garantia (seguro-garantia, caução, fiança)", r"ap[oó]lice|seguro[- ]garantia|cau[cç][aã]o|fian[cç]a banc|garantia (de|da) proposta"),
    ("Preço acima do estimado / não negociou", r"acima d[oa] (valor|pre[cç]o) (estimado|m[aá]ximo|de refer)|n[aã]o (aceitou|respondeu a|houve) (a )?negocia|aus[eê]ncia de negocia|impossibilidade de negocia|preço superior"),
    ("Preço inexequível", r"inexequ"),
    ("Documento vencido", r"vencid|validade (expirada|vencida)|fora do prazo de validade"),
    ("Atestado de capacidade técnica", r"atestado|capacidade t[eé]cnica|acervo|\bcat\b|experi[eê]ncia anterior"),
    ("Qualificação econômico-financeira", r"balan[cç]o|[ií]ndices?|liquidez|patrim[oô]nio l[ií]quido|capital (social|m[ií]nimo)|fal[eê]ncia|recupera[cç][aã]o judicial"),
    ("Regularidade fiscal e trabalhista", r"regularidade fiscal|\bcnd\b|certid[aã]o negativa|fgts|\bcrf\b|trabalhist|cndt|fazenda|d[eé]bitos|tribut"),
    ("Habilitação jurídica", r"contrato social|ato constitutivo|estatuto|procura[cç][aã]o|representante legal|\bccmei\b"),
    ("Registro, alvará ou licença técnica", r"\bcrea\b|\bcau\b|\bcrf\b|conselho|alvar[aá]|licen[cç]a (sanit|ambient|de funcion)|anvisa|registro (no|na|junto)|autoriza[cç][aã]o de funcionamento"),
    ("Produto fora da especificação (catálogo, amostra, marca)", r"cat[aá]logo|amostra|ficha t[eé]cnica|especifica[cç]|marca|modelo|laudo|n[aã]o atende ao (descritivo|termo)|prospecto|folder"),
    ("Proposta ou planilha irregular", r"planilha|proposta (ajustada|readequada|final|atualizada)|composi[cç][aã]o de custos|bdi|encargos"),
    ("Declarações", r"declara[cç]"),
    ("Não enviou no prazo / não respondeu", r"prazo|n[aã]o (enviou|anexou|encaminhou|respondeu|se manifestou|compareceu)|deixou de (enviar|anexar|encaminhar)|ausente|abandon|inerte|convoca[cç][aã]o"),
    ("SICAF / cadastro", r"sicaf|cadastro|crc"),
    ("Deixou de apresentar documentos (geral)", r"deixou de apresentar|n[aã]o apresent|aus[eê]ncia d[eo]s? documento|documenta[cç][aã]o incompleta|documentos de habilita"),
]
CAT_RE = [(n, re.compile(p, re.I)) for n, p in CATEGORIAS]


def categoria(motivo):
    for n, r in CAT_RE:
        if r.search(motivo):
            return n
    return "Outros"


def get(url, tentativas=3, timeout=90):
    for i in range(tentativas):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "radar-licitacoes/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (404, 400):
                return None
        except Exception:
            pass
        time.sleep(2 * (i + 1))
    return None


def textos_pdf(conteudo, max_paginas=250):
    pdfs = []
    if conteudo[:4] == b"%PDF":
        pdfs = [conteudo]
    elif conteudo[:2] == b"PK":
        try:
            z = zipfile.ZipFile(io.BytesIO(conteudo))
            nomes = [n for n in z.namelist() if n.lower().endswith(".pdf")]
            pdfs = [z.read(n) for n in nomes[:6]]
        except zipfile.BadZipFile:
            pass
    out = []
    for p in pdfs:
        try:
            rd = PdfReader(io.BytesIO(p))
            out.append("\n".join((pg.extract_text() or "") for pg in rd.pages[:max_paginas]))
        except Exception:
            continue
    return "\n".join(out)


def cnpj_valido(d):
    if len(d) != 14 or len(set(d)) == 1:
        return False
    def dv(base, pesos):
        r = sum(int(x) * p for x, p in zip(base, pesos)) % 11
        return "0" if r < 2 else str(11 - r)
    p1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    return d[12] == dv(d[:12], p1) and d[13] == dv(d[:13], [6] + p1)


def limpar_cnpj(c):
    d = re.sub(r"\D", "", c)
    return d if cnpj_valido(d) else None


def fmt_cnpj(d):
    return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"


NOME_ANTES = re.compile(r"([A-ZÀ-Ú0-9][A-ZÀ-Ú0-9&.,'´` \-/]{3,90}?)\s*[-–(|]?\s*(?:CNPJ[: nº°.]*)?$")
EVENTO_NOME = re.compile(r"([A-ZÀ-Ú0-9][A-ZÀ-Ú0-9&.,'´` \-/()]{3,120}?)\s+(inabilitad[oa]|desclassificad[oa]|recusad[oa])\.?\s*(?:-|,)?\s*Motivo\s*:\s*(.{8,500}?)(?=\s\d{2}/\d{2}/\d{4}|\s\|\s|\s(?:PREGOEIRO|AGENTE|SISTEMA|MOVIMENTOS|Item:|Fase)\b|$)", re.I)
EVENTO_LICITANTE = re.compile(r"(Inabilitad[oa]|Desclassificad[oa]|Recusad[oa])\s+(?:o|a)\s+(?:licitante|fornecedor|empresa|proposta d[oa]\s+\w+)\s+(.{3,120}?)\s+pelo motivo\s*:?\s*(.{8,500}?)(?=\s\d{2}/\d{2}/\d{4}|\s(?:Fase|Intenção|Habilitad)|$)", re.I)
EVENTO_CNPJ = re.compile(r"(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})[^.]{0,120}?(Inabilita[cç][aã]o|Desclassifica[cç][aã]o|Recusa)\s*:\s*(.{8,500}?)(?=\s\d{2}/\d{2}/\d{4}|\s\d{2}\.\d{3}\.\d{3}/|$)", re.I)


def extrair(texto):
    plano = re.sub(r"\s+", " ", texto)
    eventos = []
    for m in EVENTO_NOME.finditer(plano):
        nome = re.sub(r"^.*?(?:PREGOEIRO|AGENTE DE CONTRATA[CÇ][AÃ]O|PARTICIPANTE)\s*\|?\s*", "", m.group(1), flags=re.I).strip(" -|")
        eventos.append({"empresa": nome[:120], "cnpj": None, "tipo": m.group(2).lower()[:6], "motivo": m.group(3).strip()})
    for m in EVENTO_LICITANTE.finditer(plano):
        eventos.append({"empresa": m.group(2).strip()[:120], "cnpj": None, "tipo": m.group(1).lower()[:6], "motivo": m.group(3).strip()})
    for m in EVENTO_CNPJ.finditer(plano):
        eventos.append({"empresa": None, "cnpj": limpar_cnpj(m.group(1)), "tipo": m.group(2).lower()[:6], "motivo": m.group(3).strip()})
    # participantes: CNPJs com o nome que aparece logo antes
    parts = {}
    for m in CNPJ.finditer(texto):
        d = limpar_cnpj(m.group(0))
        if not d or d in parts:
            continue
        antes = texto[max(0, m.start() - 140):m.start()].split("\n")
        nome = ""
        for linha in reversed(antes):
            linha = linha.strip(" -|:")
            if re.search(r"[A-Za-zÀ-ú]{3}", linha) and not re.search(r"CNPJ|Documento|Raz[aã]o Social|Fornecedor$|\d{2}/\d{2}/\d{4}|\d{2}:\d{2}", linha, re.I):
                nome = re.sub(r"^\s*\d+\s+", "", linha)
                nome = re.split(r"\s+-\s+Tipo:|\s+Tipo:|\s+LC123", nome)[0][-90:].strip()
                break
        parts[d] = nome
    # dedup eventos
    vistos, unicos = set(), []
    for e in eventos:
        k = ((e["empresa"] or e["cnpj"] or "").lower()[:40], e["motivo"][:60].lower())
        if k in vistos or len(e["motivo"]) < 8:
            continue
        vistos.add(k)
        e["tipo"] = "inabilitação" if e["tipo"].startswith("inab") else "desclassificação" if e["tipo"].startswith("desc") else "recusa"
        e["motivo"] = e["motivo"][:400]
        e["categoria"] = categoria(e["motivo"])
        unicos.append(e)
    return unicos, parts


def arquivos_ata(r):
    corpo = get(f"{API}/orgaos/{r['cnpj']}/compras/{r['ano']}/{r['seq']}/arquivos")
    try:
        docs = json.loads(corpo) if corpo else []
    except json.JSONDecodeError:
        return []
    sel = []
    for d in docs:
        tit = f"{d.get('titulo') or ''} {d.get('tipoDocumentoNome') or ''}"
        if d.get("statusAtivo") is False:
            continue
        if "sessão pública" in (d.get("tipoDocumentoNome") or "").lower() or (ATA_TITULO.search(tit) and not NAO_ATA.search(d.get("titulo") or "")):
            sel.append(d)
    return sel[-4:]  # as mais recentes costumam ser as finais


def buscar_antigas(pasta, feitos, quantas):
    """Licitações publicadas há 45–150 dias (sessões já encerradas), percorrendo um dia por vez para trás."""
    sys.path.insert(0, AQUI)
    from segmentos import classificar
    cur_f = os.path.join(pasta, "cursor.txt")
    hoje = dt.date.today()
    dia = dt.date.fromisoformat(open(cur_f).read().strip()) if os.path.exists(cur_f) else hoje - dt.timedelta(days=45)
    if dia < hoje - dt.timedelta(days=150):
        dia = hoje - dt.timedelta(days=45)
    out = []
    while len(out) < quantas and dia >= hoje - dt.timedelta(days=150):
        for mod in (6, 4):
            pag = 1
            while len(out) < quantas:
                corpo = get("https://pncp.gov.br/api/consulta/v1/contratacoes/publicacao?" + urllib.parse.urlencode({"dataInicial": dia.strftime("%Y%m%d"), "dataFinal": dia.strftime("%Y%m%d"), "codigoModalidadeContratacao": mod, "pagina": pag, "tamanhoPagina": 50}))
                try:
                    j = json.loads(corpo) if corpo else {}
                except json.JSONDecodeError:
                    j = {}
                for c in j.get("data") or []:
                    uo = c.get("unidadeOrgao") or {}; oe = c.get("orgaoEntidade") or {}
                    r = {"id": c.get("numeroControlePNCP"), "cnpj": oe.get("cnpj"), "ano": c.get("anoCompra"), "seq": c.get("sequencialCompra"),
                         "uf": uo.get("ufSigla"), "mun": uo.get("municipioNome"), "mod": c.get("modalidadeNomeHtml") or c.get("modalidadeNome"),
                         "obj": " ".join((c.get("objetoCompra") or "").split())[:300], "org": oe.get("razaoSocial"),
                         "enc": c.get("dataEncerramentoProposta"), "vest": c.get("valorTotalEstimado")}
                    if r["id"] and r["id"] not in feitos and (c.get("valorTotalHomologado") or 0) > 0:
                        r["seg"] = classificar(r["obj"])
                        out.append(r)
                if not j.get("data") or pag >= (j.get("totalPaginas") or 1) or pag >= 6:
                    break
                pag += 1
                time.sleep(0.2)
        dia -= dt.timedelta(days=1)
    open(cur_f, "w").write(dia.isoformat())
    print(f"  {len(out)} licitações antigas (com resultado homologado) adicionadas; cursor em {dia}", file=sys.stderr)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dados", default=None)
    ap.add_argument("--pasta", default=os.path.normpath(os.path.join(AQUI, "..", "atas")))
    ap.add_argument("--max", type=int, default=300, help="máximo de licitações verificadas por execução")
    ap.add_argument("--min-dias", type=int, default=4, help="só licitações encerradas há pelo menos N dias")
    ap.add_argument("--saida-pagina", default=None, help="onde gravar aprendizados.json")
    a = ap.parse_args()
    os.makedirs(a.pasta, exist_ok=True)
    pc = os.path.join(a.pasta, "processados.txt")
    feitos = set(open(pc, encoding="utf-8").read().split()) if os.path.exists(pc) else set()
    if a.dados and os.path.exists(a.dados):
        lic = json.load(open(a.dados, encoding="utf-8"))
        limite = (dt.datetime.now() - dt.timedelta(days=a.min_dias)).isoformat()
        alvo = [r for r in lic if r.get("cnpj") and r.get("ano") and r.get("seq") and r.get("enc") and r["enc"] < limite
                and MODS_COMPETITIVAS.search(r.get("mod") or "") and r["id"] not in feitos]
        alvo.sort(key=lambda r: r["enc"])  # as mais antigas primeiro: têm mais chance de já ter ata
    else:
        alvo = []
    if len(alvo) < a.max:
        alvo += buscar_antigas(a.pasta, feitos, a.max - len(alvo))
    alvo = alvo[: a.max]
    print(f"{len(alvo)} licitações para verificar ({len(feitos)} já verificadas)", file=sys.stderr)
    fc = open(os.path.join(a.pasta, "casos.jsonl"), "a", encoding="utf-8")
    fp = open(os.path.join(a.pasta, "participantes.jsonl"), "a", encoding="utf-8")
    fpc = open(pc, "a", encoding="utf-8")
    n_atas = n_casos = 0
    for i, r in enumerate(alvo, 1):
        base = {"lic": r["id"], "uf": r.get("uf"), "mun": r.get("mun"), "seg": r.get("seg"), "mod": r.get("mod"), "obj": (r.get("obj") or "")[:160], "org": r.get("org"), "enc": (r.get("enc") or "")[:10], "vest": r.get("vest")}
        try:
            for d in arquivos_ata(r):
                cont = get(d.get("url") or "", timeout=120)
                if not cont or len(cont) > 30_000_000:
                    continue
                txt = textos_pdf(cont)
                if len(txt) < 200:
                    continue
                n_atas += 1
                eventos, parts = extrair(txt)
                for e in eventos:
                    if e["cnpj"] and not e["empresa"]:
                        e["empresa"] = parts.get(e["cnpj"]) or None
                    fc.write(json.dumps({**base, **e, "ata": d.get("url"), "ata_titulo": (d.get("titulo") or "")[:80]}, ensure_ascii=False) + "\n")
                    n_casos += 1
                for c, nome in parts.items():
                    if c == r.get("cnpj"):
                        continue  # o próprio órgão
                    fp.write(json.dumps({"lic": r["id"], "uf": r.get("uf"), "seg": r.get("seg"), "cnpj": c, "nome": nome, "enc": base["enc"]}, ensure_ascii=False) + "\n")
                time.sleep(0.2)
        except Exception as e:  # noqa: BLE001
            print(f"  erro em {r['id']}: {e!r}", file=sys.stderr)
        fpc.write(r["id"] + "\n")
        if i % 25 == 0:
            print(f"  {i}/{len(alvo)} · atas lidas {n_atas} · casos {n_casos}", file=sys.stderr)
            fc.flush(); fp.flush(); fpc.flush()
    fc.close(); fp.close(); fpc.close()
    print(f"Pronto: {n_atas} atas, {n_casos} casos novos", file=sys.stderr)
    if a.saida_pagina:
        gerar_resumo(a.pasta, a.saida_pagina)


def limpar_empresa(c):
    nome = c.get("empresa") or ""
    m = CNPJ.search(nome)
    if m and not c.get("cnpj"):
        c["cnpj"] = limpar_cnpj(m.group(0))
    nome = re.sub(r"^.*?(?:O fornecedor\s+)?\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\s*-\s*", "", nome)
    nome = re.sub(r"^(?:\d+\s+)?(?:PREGOEIRO|AGENTE DE CONTRATA[CÇ][AÃ]O|SISTEMA|Sistema)\s+", "", nome)
    nome = re.sub(r"\s+foi$", "", nome).strip(" -|")
    c["empresa"] = nome or None
    return c


def amostra_casos(casos, por_sub=60, total=6000):
    """Para a página: os casos mais recentes de CADA subsegmento (para o cruzamento achar precedentes parecidos),
    completando com os mais recentes em geral. Só casos com motivo útil."""
    util = [c for c in casos if len(c.get("motivo") or "") >= 15 and c.get("categoria") not in ("Desistência do próprio licitante",)]
    util.sort(key=lambda c: c.get("enc") or "", reverse=True)
    escolhidos, ids, cont = [], set(), collections.Counter()
    for c in util:
        k = (c.get("seg"), c.get("sub"))
        if cont[k] < por_sub:
            cont[k] += 1; escolhidos.append(c); ids.add(id(c))
    for c in util:
        if len(escolhidos) >= total:
            break
        if id(c) not in ids:
            escolhidos.append(c)
    campos = ("lic", "uf", "mun", "seg", "sub", "mod", "obj", "org", "enc", "empresa", "cnpj", "tipo", "motivo", "categoria", "ata", "fonte")
    return [{k: c.get(k) for k in campos if c.get(k) is not None} for c in escolhidos[:total]]


def gerar_resumo(pasta, saida):
    sys.path.insert(0, AQUI)
    from segmentos import classificar_completo
    brutos = [json.loads(l) for l in open(os.path.join(pasta, "casos.jsonl"), encoding="utf-8") if l.strip()]
    casos, vistos = [], set()
    for c in brutos:
        c = limpar_empresa(c)
        c["categoria"] = categoria(c.get("motivo") or "")
        if c.get("obj"):
            c["seg"], c["sub"], _ = classificar_completo(c["obj"])
        k = (c["lic"], (c.get("empresa") or c.get("cnpj") or "").lower()[:40], (c.get("motivo") or "")[:60].lower())
        if k in vistos:
            continue
        vistos.add(k)
        casos.append(c)
    seg_lic = {c["lic"]: c["seg"] for c in casos if c.get("seg")}
    parts = [p for p in (json.loads(l) for l in open(os.path.join(pasta, "participantes.jsonl"), encoding="utf-8") if l.strip()) if cnpj_valido(p.get("cnpj") or "")]
    for p in parts:
        p["seg"] = seg_lic.get(p.get("lic"), p.get("seg"))
    n_lic = len(set(open(os.path.join(pasta, "processados.txt"), encoding="utf-8").read().split()))
    # empresas: participações (uma por licitação) e problemas
    RUIDO = re.compile(r"d[uú]vida|prezad|\breais\b|munic[ií]pio|prefeitura|secretaria|c[aâ]mara municipal|fundo municipal|^[^A-Za-zÀ-ú0-9]|[,:;)]$|fornecedor|valor|quantidade|situa[cç][aã]o|concorr[eê]ncia|pre[cç]o|\bitem\b|\blote\b|marca|ofertad|proposta|documento|raz[aã]o social|habilitad|classifica|esclarecimento|pregoeiro|cnpj|data|hora", re.I)
    nomes_cnpj = collections.defaultdict(collections.Counter)
    for p in parts:
        n = (p.get("nome") or "").strip()
        if n and not RUIDO.search(n) and len(n) >= 4 and re.search(r"[A-Za-zÀ-ú]{3}", n):
            nomes_cnpj[p["cnpj"]][n] += 1
    for c in casos:
        if c.get("cnpj") and c.get("empresa") and not RUIDO.search(c["empresa"]):
            nomes_cnpj[c["cnpj"]][c["empresa"]] += 2
    vistos_p = set(); unicos = []
    for p in parts:
        k = (p["lic"], p["cnpj"])
        if k in vistos_p:
            continue
        vistos_p.add(k); p["nome"] = nomes_cnpj[p["cnpj"]].most_common(1)[0][0] if nomes_cnpj[p["cnpj"]] else ""
        unicos.append(p)
    parts = unicos
    emp = {}
    for p in parts:
        e = emp.setdefault(p["cnpj"], {"cnpj": fmt_cnpj(p["cnpj"]), "nome": p.get("nome") or "", "part": 0, "inab": 0, "desc": 0, "ufs": collections.Counter(), "segs": collections.Counter(), "ult": ""})
        e["part"] += 1; e["ufs"][p.get("uf")] += 1; e["segs"][p.get("seg")] += 1; e["ult"] = max(e["ult"], p.get("enc") or "")
        if not e["nome"] and p.get("nome"):
            e["nome"] = p["nome"]
    nomes = {}
    for c in casos:
        if c.get("cnpj") and c["cnpj"] in emp:
            emp[c["cnpj"]]["inab" if c["tipo"] == "inabilitação" else "desc"] += 1
        elif c.get("empresa"):
            nomes[c["empresa"].lower()[:30]] = c
    empresas = []
    for e in emp.values():
        empresas.append({"cnpj": e["cnpj"], "nome": e["nome"][:90], "part": e["part"], "inab": e["inab"], "desc": e["desc"],
                         "ufs": [u for u, _ in e["ufs"].most_common(3) if u], "segs": [s for s, _ in e["segs"].most_common(2) if s], "ult": e["ult"]})
    empresas.sort(key=lambda e: (-e["part"], e["nome"]))
    resumo = {
        "gerado_em": dt.datetime.now().isoformat(timespec="seconds"),
        "licitacoes_verificadas": n_lic,
        "atas_com_casos": len(set(c["lic"] for c in casos)),
        "total_casos": len(casos),
        "categorias": collections.Counter(c["categoria"] for c in casos).most_common(),
        "por_subsegmento": {f"{a} › {b}": collections.Counter(c["categoria"] for c in casos if c.get("seg") == a and c.get("sub") == b).most_common(6) for a, b in set((c.get("seg"), c.get("sub")) for c in casos) if a and b},
        "por_segmento": {s: collections.Counter(c["categoria"] for c in casos if c.get("seg") == s).most_common(6) for s in set(c.get("seg") for c in casos) if s},
        "casos": amostra_casos(casos),
        "empresas": empresas[:4000],
        "total_empresas": len(empresas),
    }
    os.makedirs(os.path.dirname(os.path.abspath(saida)), exist_ok=True)
    with open(saida, "w", encoding="utf-8") as f:
        json.dump(resumo, f, ensure_ascii=False, separators=(",", ":"))
    print(f"Resumo: {len(casos)} casos, {len(empresas)} empresas → {saida}", file=sys.stderr)


if __name__ == "__main__":
    main()
