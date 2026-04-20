from __future__ import annotations

import logging
from typing import Optional

from .base import EmbeddingModel

logger = logging.getLogger("ai-memory.embedding")


class LocalEmbedding(EmbeddingModel):
    """基于 sentence-transformers 的本地嵌入模型"""

    MODEL_DIMENSIONS = {
        "all-MiniLM-L6-v2": 384,
        "BAAI/bge-small-zh-v1.5": 512,
        "nomic-ai/nomic-embed-text-v1.5": 768,
    }

    def __init__(
        self,
        model_name: str = "BAAI/bge-small-zh-v1.5",
        device: str = "cpu",
        cache_dir: Optional[str] = None,
        lazy_load: bool = True,
    ):
        self.model_name = model_name
        self.device = device
        self.cache_dir = cache_dir
        self._model = None
        self._dim = self.MODEL_DIMENSIONS.get(model_name, 512)

        if not lazy_load:
            self._load_model()

    def _load_model(self):
        if self._model is not None:
            return

        logger.info(f"加载嵌入模型: {self.model_name} (device={self.device})")
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(
                self.model_name,
                device=self.device,
                cache_folder=self.cache_dir,
            )
            self._dim = self._model.get_sentence_embedding_dimension()
            logger.info(f"模型加载完成, 维度={self._dim}")
        except ImportError:
            raise RuntimeError(
                "sentence-transformers 未安装。"
                "运行: pip install sentence-transformers"
            )

    def encode(self, text: str) -> list[float]:
        self._load_model()
        embedding = self._model.encode(text, normalize_embeddings=True)
        return embedding.tolist()

    def encode_batch(self, texts: list[str]) -> list[list[float]]:
        self._load_model()
        embeddings = self._model.encode(
            texts,
            normalize_embeddings=True,
            batch_size=32,
            show_progress_bar=False,
        )
        return [e.tolist() for e in embeddings]

    def dimension(self) -> int:
        return self._dim
