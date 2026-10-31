"""
Indexa o banco para a busca híbrida:
  1. fornecedores_fts  -> índice FTS5 (busca lexical / BM25)
  2. embeddings        -> vetores normalizados (busca semântica)

Os dois índices usam um "texto de busca" que tira da descrição o que já é tratado
por filtro/rerank (cidade, preço, avaliação, disponibilidade). Assim a similaridade
fica focada em O QUE o fornecedor faz, e não em onde ele está.

Uso:
    python indexar.py                  # bge-m3 na CPU (sentence-transformers) — padrão
    python indexar.py --backend sglang # bge-m3 servido pelo SGLang (GPUs com mais VRAM)
    python indexar.py --backend lsa    # fallback offline, só para teste
"""
import argparse
import re
import sqlite3

from embeddings import EMBED_URL, criar_embedder

DB_PATH = "fornecedores_cafe.db"

PREFIXOS_DESCARTE = ("Atende", "Preço médio", "Cobra em média", "Avaliação média",
                     "Disponibilidade", "Certificações", "Segmento:")


def texto_de_busca(row):
    frases = re.split(r"(?<=\.)\s+", row["descricao"])[1:]  # 1ª frase = nome/cidade/anos
    frases = [f for f in frases if not f.startswith(PREFIXOS_DESCARTE)]
    partes = [f"{row['tipo']} ({row['categoria']}).", *frases]
    if row["certificacoes"]:
        partes.append(f"Registros e certificações: {row['certificacoes']}.")
    return " ".join(partes)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DB_PATH)
    ap.add_argument("--backend", choices=["st", "sglang", "lsa"], default="st")
    ap.add_argument("--modelo", default=None, help="padrão: BAAI/bge-m3")
    ap.add_argument("--embed-url", default=EMBED_URL)
    args = ap.parse_args()

    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row
    rows = con.execute("SELECT id, tipo, categoria, especialidades, descricao, certificacoes "
                       "FROM fornecedores ORDER BY id").fetchall()
    textos = [texto_de_busca(r) for r in rows]

    # --- FTS5 ---
    con.executescript("""
        DROP TABLE IF EXISTS fornecedores_fts;
        CREATE VIRTUAL TABLE fornecedores_fts USING fts5(
            tipo, especialidades, texto,
            tokenize = "unicode61 remove_diacritics 2"
        );
    """)
    con.executemany("INSERT INTO fornecedores_fts(rowid, tipo, especialidades, texto) VALUES (?,?,?,?)",
                    [(r["id"], r["tipo"], r["especialidades"] or "", t) for r, t in zip(rows, textos)])

    # --- Embeddings ---
    emb = criar_embedder(args.backend, args.modelo, args.embed_url)
    emb.fit(textos)
    vetores = emb.docs(textos)
    con.executescript("""
        DROP TABLE IF EXISTS embeddings;
        CREATE TABLE embeddings (
            fornecedor_id INTEGER PRIMARY KEY REFERENCES fornecedores(id),
            modelo        TEXT    NOT NULL,
            dim           INTEGER NOT NULL,
            texto         TEXT    NOT NULL,   -- texto que gerou o vetor
            vetor         BLOB    NOT NULL    -- float32 normalizado
        );
    """)
    con.executemany("INSERT INTO embeddings VALUES (?,?,?,?,?)",
                    [(r["id"], emb.nome, v.shape[0], t, v.tobytes())
                     for r, t, v in zip(rows, textos, vetores)])
    con.commit()
    con.close()
    print(f"{len(rows)} fornecedores indexados | modelo={emb.nome} | dim={vetores.shape[1]}")


if __name__ == "__main__":
    main()
