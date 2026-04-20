from __future__ import annotations

from abc import ABC, abstractmethod


class EmbeddingModel(ABC):
    @abstractmethod
    def encode(self, text: str) -> list[float]:
        """将文本编码为向量"""

    @abstractmethod
    def encode_batch(self, texts: list[str]) -> list[list[float]]:
        """批量编码"""

    @abstractmethod
    def dimension(self) -> int:
        """返回向量维度"""
