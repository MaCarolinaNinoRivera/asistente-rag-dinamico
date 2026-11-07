from typing import Iterable, Optional

CARACTERES_POR_TOKEN = 4

def estimar_tokens(textos: Iterable[str]) -> int:
    return max(1, sum(len(t) for t in textos) // CARACTERES_POR_TOKEN)

def calcular_costo(tokens_entrada: int, tokens_salida: int, precios: Optional[dict]) -> Optional[float]:
    """None si el modelo no tiene precio configurado (mejor 'sin precio' que un costo inventado)."""
    if not precios or precios.get("precio_entrada_millon") is None:
        return None
    entrada = float(precios["precio_entrada_millon"])
    salida = float(precios.get("precio_salida_millon") or 0)
    return round(((tokens_entrada or 0) * entrada + (tokens_salida or 0) * salida) / 1_000_000, 6)
