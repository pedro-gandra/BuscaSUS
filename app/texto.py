"""Normalização de texto compartilhada entre ETL e busca."""
import re
import unicodedata

STOP = {"de", "da", "do", "das", "dos", "no", "na", "nos", "nas", "em", "a", "o", "e"}


def sem_acento(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c))


def tokens(s: str) -> list[str]:
    """Minúsculas, sem acento, só [a-z0-9], sem palavras vazias."""
    s = re.sub(r"[^a-z0-9]+", " ", sem_acento(s).lower())
    return [t for t in s.split() if t not in STOP]
