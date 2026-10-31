"""
Backends de embedding.

- "st"     : sentence-transformers no próprio processo (padrão: BAAI/bge-m3 na CPU) — o padrão para GPU de 8 GB,
             que fica inteira para o LLM. Use EMBED_DEVICE=cuda se sobrar VRAM.
- "sglang" : servidor SGLang com endpoint OpenAI /v1/embeddings (BAAI/bge-m3) — para GPUs maiores.
- "lsa"    : TF-IDF de n-gramas de caracteres + SVD. Fallback offline, só para testar o pipeline.

Os vetores densos do bge-m3 são os mesmos nos backends "st" e "sglang".
"""
import os
import pickle

import numpy as np

MODELO_PADRAO = "BAAI/bge-m3"                      # backend "st"
EMBED_DEVICE = os.getenv("EMBED_DEVICE", "cpu")    # cpu por padrão: não disputa VRAM com o LLM
MODELO_SGLANG = "BAAI/bge-m3"                      # backend "sglang"
EMBED_URL = os.getenv("EMBED_URL", "http://127.0.0.1:30001/v1")
ARQ_LSA = "modelo_lsa.pkl"


def _normaliza(m):
    m = np.asarray(m, dtype=np.float32)
    n = np.linalg.norm(m, axis=-1, keepdims=True)
    n[n == 0] = 1
    return m / n


class EmbedderST:
    def __init__(self, nome=MODELO_PADRAO, device=EMBED_DEVICE):
        from sentence_transformers import SentenceTransformer
        self.nome = nome
        self._m = SentenceTransformer(nome, device=device)
        self._m.max_seq_length = 512      # nossos textos são curtos; limita memória e tempo
        self._e5 = "e5" in nome.lower()  # modelos E5 exigem prefixos query:/passage:

    def fit(self, textos):
        pass

    def docs(self, textos):
        if self._e5:
            textos = [f"passage: {t}" for t in textos]
        return _normaliza(self._m.encode(textos, batch_size=32, show_progress_bar=True))

    def query(self, texto):
        if self._e5:
            texto = f"query: {texto}"
        return _normaliza(self._m.encode([texto]))[0]


class EmbedderSGLang:
    """bge-m3 servido pelo SGLang. O bge-m3 não usa prefixo de query/passage."""

    def __init__(self, modelo=MODELO_SGLANG, url=EMBED_URL, lote=32):
        from openai import OpenAI
        self.modelo = modelo
        self.nome = f"sglang:{modelo}"
        self.lote = lote
        self._c = OpenAI(base_url=url, api_key=os.getenv("SGLANG_API_KEY", "EMPTY"))

    def fit(self, textos):
        pass

    def _embed(self, textos):
        vetores = []
        for i in range(0, len(textos), self.lote):
            r = self._c.embeddings.create(model=self.modelo, input=textos[i:i + self.lote])
            vetores.extend(d.embedding for d in sorted(r.data, key=lambda d: d.index))
        return _normaliza(vetores)

    def docs(self, textos):
        return self._embed(textos)

    def query(self, texto):
        return self._embed([texto])[0]


class EmbedderLSA:
    nome = "lsa-tfidf"

    def __init__(self, carregar=False):
        self._vec = self._svd = None
        if carregar:
            with open(ARQ_LSA, "rb") as f:
                self._vec, self._svd = pickle.load(f)

    def fit(self, textos):
        from sklearn.decomposition import TruncatedSVD
        from sklearn.feature_extraction.text import TfidfVectorizer
        self._vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), strip_accents="unicode",
                                    sublinear_tf=True, min_df=2)
        X = self._vec.fit_transform(textos)
        self._svd = TruncatedSVD(n_components=min(200, X.shape[0] - 1), random_state=42).fit(X)
        with open(ARQ_LSA, "wb") as f:
            pickle.dump((self._vec, self._svd), f)

    def docs(self, textos):
        return _normaliza(self._svd.transform(self._vec.transform(textos)))

    def query(self, texto):
        return self.docs([texto])[0]


def criar_embedder(backend="st", modelo=None, url=EMBED_URL):
    if backend == "sglang":
        return EmbedderSGLang(modelo or MODELO_SGLANG, url)
    if backend == "st":
        return EmbedderST(modelo or MODELO_PADRAO)
    if backend == "lsa":
        return EmbedderLSA()
    raise ValueError(f"backend desconhecido: {backend}")


def carregar_embedder(nome_modelo):
    """Recria o embedder usado na indexação a partir do nome gravado no banco."""
    if nome_modelo == EmbedderLSA.nome:
        return EmbedderLSA(carregar=True)
    if nome_modelo.startswith("sglang:"):
        return EmbedderSGLang(nome_modelo.split(":", 1)[1])
    return EmbedderST(nome_modelo)
