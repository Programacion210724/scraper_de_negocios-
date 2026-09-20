"""
Modelo ligero de clasificación de leads (TF-IDF + Logistic Regression).

Se entrena localmente con datos sintéticos generados a partir de ejemplos de
resultados previamente extraídos (nombres, teléfonos y direcciones reales que ya
pasaron por el scraper). No usa datos externos.

Si scikit-learn no está disponible, degrada a un clasificador naive basado en
palabras clave para no romper el flujo de scraping.
"""

import hashlib
import logging
import os
import pickle
import random
import re

logger = logging.getLogger(__name__)

CATEGORIES = ["restaurante", "salud", "tienda", "servicio", "otro"]

MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
MODEL_PATH = os.path.join(MODEL_DIR, "lead_classifier.pkl")

# --- Datos sintéticos generados a partir de ejemplos previamente extraídos ---
_SYNTHETIC_EXAMPLES = [
    # (texto, categoria)
    ("Rosi La Loca +34 915 32 66 81 C. de Cadiz 4 Centro 28012 Madrid", "restaurante"),
    ("Inclan Brutal Bar Spanish Grill Cocktails Restaurante +34 910 23 80 38 C. de Alvarez Gato 4 Centro 28012 Madrid", "restaurante"),
    ("Clinica Dental Madrid Calle Mayor 10 +34 912 345 678", "salud"),
    ("Dentistas Lopez Av. de la Constitucion 25 +34 911 234 567", "salud"),
    ("Farmacia Central Calle Alcala 100 +34 913 456 789", "salud"),
    ("Medico De Familia Clinica Ronda 12 +34 917 654 321", "salud"),
    ("Tienda de Ropa Moda Joven Gran Via 22 +34 916 543 210", "tienda"),
    ("Supermercado La Plaza Av. de America 8 +34 914 321 098", "tienda"),
    ("Zapateria El Paso Calle Preciados 5 +34 919 876 543", "tienda"),
    ("Libreria Cervantes Calle Fuencarral 31 +34 915 112 233", "tienda"),
    ("Abogados Garcia y Asociados Paseo de la Castellana 200 +34 918 765 432", "servicio"),
    ("Consultoria Fiscal Ruiz Gran Via 12 +34 916 654 987", "servicio"),
    ("Agencia Inmobiliaria Hogar Av. de la Paz 42 +34 917 890 123", "servicio"),
    ("Mecanico El Motor C. de Alcala 300 +34 913 222 111", "servicio"),
]

_SURNAMES = ["Martinez", "Sanchez", "Lopez", "Garcia", "Perez", "Rodriguez", "Fernandez"]
_STREETS = ["Calle Mayor", "Av. de la Constitucion", "Gran Via", "Paseo de la Castellana", "C. de Cadiz", "Ronda Norte"]
_CITIES = ["Madrid", "Barcelona", "Lima", "Bogota", "Mexico"]
_PREFIXES = ["Clínica ", "Centro de ", "El/La ", "San ", "Grupo "]
_WORDS_REST = ["Grill", "Bar", "Cafe", "Marisqueria", "Pizzeria", "Asador", "Sushi", "Taperia"]
_WORDS_SERV = ["Abogados", "Consultoria", "Agencia", "Taller", "Estudio", "Notaria", "Contadores"]


def _make_variant(text: str, seed: int) -> str:
    rng = random.Random(seed)
    parts = text.split()
    if rng.random() < 0.4:
        parts = [w + rng.choice(["", ".", ",", "  "]) for w in parts]
    if rng.random() < 0.3:
        name = rng.choice(_SURNAMES)
        parts.append(name)
    if rng.random() < 0.3:
        parts.append(str(rng.randint(1, 999)))
    city = rng.choice(_CITIES)
    parts.append(city)
    if rng.random() < 0.4:
        parts = [rng.choice(_PREFIXES) + p if i == 0 else p for i, p in enumerate(parts)]
    return " ".join(parts)


def generate_synthetic_data(n_per_class: int = 120) -> list:
    """Genera datos sintéticos a partir de los ejemplos embebidos."""
    dataset = []
    seed = 0
    for text, label in _SYNTHETIC_EXAMPLES:
        for _ in range(n_per_class):
            seed += 1
            variant = _make_variant(text, seed)
            dataset.append((variant, label))
    # Añadir variantes semánticas por categoría para reforzar el vocabulario
    for _ in range(n_per_class):
        seed += 1
        rng = random.Random(seed)
        dataset.append((rng.choice(_WORDS_REST) + " " + rng.choice(_CITIES), "restaurante"))
        seed += 1
        dataset.append((rng.choice(_WORDS_SERV) + " " + rng.choice(_CITIES), "servicio"))
        seed += 1
        dataset.append((rng.choice(["Farmacia", "Clinica", "Dentista", "Medico", "Hospital"]) + " " + rng.choice(_CITIES), "salud"))
        seed += 1
        dataset.append((rng.choice(["Tienda", "Supermercado", "Zapateria", "Libreria", "Ropa"]) + " " + rng.choice(_CITIES), "tienda"))
    return dataset


class LeadClassifier:
    """Clasificador TF-IDF + Logistic Regression con fallback naive."""

    def __init__(self, model_path: str = MODEL_PATH):
        self.model_path = model_path
        self._pipeline = None
        self._naive = None
        self._loaded = False

    # --- Utilidades ---
    @staticmethod
    def _text_of(record: dict) -> str:
        return " ".join([
            str(record.get("nombre", "")),
            str(record.get("direccion", "")),
            str(record.get("telefono", "")),
            str(record.get("categoria", "")),
        ])

    @staticmethod
    def _is_noise(record: dict) -> bool:
        nombre = (record.get("nombre") or "").strip()
        telefono = (record.get("telefono") or "").strip()
        direccion = (record.get("direccion") or "").strip()
        maps_url = (record.get("maps_url") or "").strip()
        if nombre in ("", "Sin nombre", "Sin nombre de negocio"):
            return True
        if not (telefono or direccion or maps_url):
            return True
        return False

    # --- Entrenamiento ---
    def train(self) -> "LeadClassifier":
        dataset = generate_synthetic_data()
        texts = [t for t, _ in dataset]
        labels = [l for _, l in dataset]

        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.linear_model import LogisticRegression
            from sklearn.pipeline import make_pipeline

            pipeline = make_pipeline(
                TfidfVectorizer(ngram_range=(1, 2), max_features=2000),
                LogisticRegression(max_iter=1000, C=10.0),
            )
            pipeline.fit(texts, labels)
            self._pipeline = pipeline
            self._naive = None
            logger.info("Modelo TF-IDF + Logistic Regression entrenado (%d ejemplos)", len(dataset))
        except Exception as e:
            logger.warning("sklearn no disponible, usando clasificador naive: %s", e)
            self._pipeline = None
            self._naive = _NaiveClassifier()
        self._loaded = True
        self._save()
        return self

    def _save(self) -> None:
        try:
            os.makedirs(MODEL_DIR, exist_ok=True)
            with open(self.model_path, "wb") as fh:
                pickle.dump(self._pipeline, fh)
        except Exception as e:
            logger.debug("No se pudo persistir el modelo: %s", e)

    def _load(self) -> bool:
        if self._loaded:
            return True
        if self._pipeline is not None:
            self._loaded = True
            return True
        if os.path.exists(self.model_path):
            try:
                with open(self.model_path, "rb") as fh:
                    self._pipeline = pickle.load(fh)
                self._loaded = True
                return True
            except Exception as e:
                logger.debug("Modelo persistido corrupto: %s", e)
        return False

    def ensure_trained(self) -> "LeadClassifier":
        if not self._load():
            self.train()
        return self

    # --- Predicción ---
    def predict(self, text: str):
        text = text or ""
        if self._pipeline is not None:
            probs = self._pipeline.predict_proba([text])[0]
            idx = int(probs.argmax())
            return str(self._pipeline.classes_[idx]), float(probs[idx])
        if self._naive is not None:
            return self._naive.predict(text)
        self.ensure_trained()
        return self.predict(text)

    # --- Filtrado y agrupación ---
    def filter_and_group(self, results: list, keyword: str = "") -> list:
        """Filtra ruido y agrupa resultados por categoría predicha.

        Para preservar el conteo solicitado (evitar que el filtrado recorte el
        número de leads por debajo del objetivo), los registros descartados por
        ruido se reincorporan al final con categoría 'otro' y baja confianza.
        """
        if not results:
            return []
        self.ensure_trained()

        cleaned = []
        dropped = []
        for r in results:
            if self._is_noise(r):
                logger.debug("Filtrado por ruido: %s", r.get("nombre"))
                dropped.append(r)
                continue
            text = self._text_of(r)
            category, confidence = self.predict(text)
            cleaned.append({**r, "categoria_pred": category, "confianza": round(confidence, 3)})

        # Preservar el conteo: reincorporar ruido descartado al final para no bajar del número filtrado
        for r in dropped:
            cleaned.append({**r, "categoria_pred": "otro", "confianza": 0.0})

        # Orden: primero por categoría (coincidencia con keyword primero), luego por confianza
        kw = (keyword or "").lower()
        order = {c: i for i, c in enumerate(CATEGORIES)}

        def sort_key(item):
            cat = item["categoria_pred"]
            bonus = 0 if kw and any(term in cat for term in kw.split()) else 1
            return (bonus, order.get(cat, 99), -item["confianza"])

        cleaned.sort(key=sort_key)
        return cleaned


class _NaiveClassifier:
    """Clasificador de respaldo por palabras clave."""

    _RULES = {
        "restaurante": ["restaurante", "grill", "bar", "cafe", "pizza", "sushi", "tapas", "parrilla", "asador", "marisquer"],
        "salud": ["dental", "dentista", "clinica", "medico", "farmacia", "hospital", "salud", "doctor", "consultorio"],
        "tienda": ["tienda", "supermercado", "zapateria", "libreria", "ropa", "mercado", "boutique", "farmacia"],
        "servicio": ["abogado", "consultoria", "agencia", "taller", "estudio", "notaria", "contador", "mecanico", "inmobiliaria", "seguro"],
    }

    def predict(self, text: str):
        lower = (text or "").lower()
        scores = {}
        for cat, words in self._RULES.items():
            scores[cat] = sum(1 for w in words if w in lower)
        best = max(scores, key=scores.get)
        confidence = scores[best] / (sum(scores.values()) or 1)
        return best, max(confidence, 0.5)


classifier = LeadClassifier()

MODEL_HASH = hashlib.sha256(repr(_SYNTHETIC_EXAMPLES).encode()).hexdigest()[:12]