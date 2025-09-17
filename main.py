import os
import json
import random
import re
from typing import List, Dict, Tuple, Set, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from starlette.templating import Jinja2Templates

# App with default docs at /docs
app = FastAPI()

# Static and templates
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")
WORDS_DIR = os.path.join(BASE_DIR, "words")
KNOWN_PATH = os.path.join(BASE_DIR, "known_words.json")

# Ensure folders exist
os.makedirs(TEMPLATES_DIR, exist_ok=True)
os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(WORDS_DIR, exist_ok=True)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# CORS (optional for local dev if needed)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"]
    ,
    allow_headers=["*"]
)

# In-memory storage
VOCAB: List[Dict[str, str]] = []
KNOWN: Set[Tuple[str, str]] = set()

class KnownBody(BaseModel):
    fr: str
    de: str


def load_known() -> Set[Tuple[str, str]]:
    if not os.path.exists(KNOWN_PATH):
        with open(KNOWN_PATH, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False)
        return set()
    try:
        with open(KNOWN_PATH, "r", encoding="utf-8") as f:
            items = json.load(f)
            result: Set[Tuple[str, str]] = set()
            for it in items:
                fr = it.get("fr")
                de = it.get("de")
                if isinstance(fr, str) and isinstance(de, str):
                    result.add((fr, de))
            return result
    except Exception:
        return set()


def save_known(known: Set[Tuple[str, str]]) -> None:
    data = [{"fr": fr, "de": de} for fr, de in sorted(list(known))]
    with open(KNOWN_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_vocab() -> List[Dict[str, str]]:
    def parse_json_relaxed(text: str):
        # Remove // line comments
        text = re.sub(r"^\s*//.*$", "", text, flags=re.MULTILINE)
        # Remove /* block comments */
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
        return json.loads(text)

    result: List[Dict[str, str]] = []
    if not os.path.isdir(WORDS_DIR):
        return result
    try:
        files_all = [f for f in os.listdir(WORDS_DIR) if f.endswith('.json')]
        # If latin.json exists, prioritize it exclusively (use Latin dataset)
        if 'latin.json' in files_all:
            files = ['latin.json']
        else:
            files = files_all
            # natural sort by embedded number in filenames like list1.json, list2.json, ...
            def file_key(name: str):
                m = re.search(r"(\d+)", name)
                return (int(m.group(1)) if m else float('inf'), name)
            files.sort(key=file_key)
    except Exception:
        files = []

    for fname in files:
        fpath = os.path.join(WORDS_DIR, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                raw = f.read()
            items = parse_json_relaxed(raw)
            if isinstance(items, list):
                for it in items:
                    if fname == 'latin.json' or 'lemma' in it or 'translation_de' in it:
                        # Latin schema mapping
                        la = (it.get("lemma") or "").strip()
                        de = (it.get("translation_de") or "").strip()
                        pos = (it.get("pos") or "").strip()
                        pp = (it.get("principal_parts") or "").strip()
                        ex = it.get("declension_example") or {}
                        ex_la = (ex.get("la") or "").strip() if isinstance(ex, dict) else ""
                        ex_de = (ex.get("de") or "").strip() if isinstance(ex, dict) else ""
                        if la and de:
                            result.append({
                                "fr": la,   # reuse 'fr' field as source term (Latin)
                                "de": de,
                                "pron": "",  # not used for Latin; keep for compatibility
                                "pos": pos,
                                "pp": pp,
                                "ex_la": ex_la,
                                "ex_de": ex_de,
                                "dataset": "latin"
                            })
                    else:
                        # FR-DE schema mapping
                        fr = (it.get("fr") or it.get("french") or it.get("fr_word") or "").strip()
                        de = (it.get("de") or it.get("german") or it.get("de_word") or "").strip()
                        pron = (it.get("pron") or it.get("pronunciation") or "").strip()
                        if fr and de:
                            result.append({"fr": fr, "de": de, "pron": pron, "dataset": "frde"})
        except Exception:
            # skip malformed file
            continue
    return result


@app.on_event("startup")
async def on_startup():
    global VOCAB, KNOWN
    VOCAB = load_vocab()
    # assign stable sequence numbers starting at 1
    for idx, it in enumerate(VOCAB, start=1):
        it["num"] = idx
    KNOWN = load_known()


@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/vocab")
async def get_vocab():
    return VOCAB


def transform_direction(direction: str, items: List[Dict[str, str]]):
    """Return items mapped to chosen direction while keeping original fields for reference."""
    if direction not in {"fr-de", "de-fr"}:
        raise HTTPException(status_code=400, detail="Invalid direction. Use fr-de or de-fr")
    mapped = []
    for it in items:
        if direction == "fr-de":
            mapped.append({
                "from": it["fr"],
                "to": it["de"],
                "pron": it.get("pron", ""),
                "fr": it["fr"],
                "de": it["de"],
                "num": it.get("num"),
                "pos": it.get("pos", ""),
                "pp": it.get("pp", ""),
                "ex_la": it.get("ex_la", ""),
                "ex_de": it.get("ex_de", ""),
                "dataset": it.get("dataset", "")
            })
        else:
            mapped.append({
                "from": it["de"],
                "to": it["fr"],
                "pron": it.get("pron", ""),
                "fr": it["fr"],
                "de": it["de"],
                "num": it.get("num"),
                "pos": it.get("pos", ""),
                "pp": it.get("pp", ""),
                "ex_la": it.get("ex_la", ""),
                "ex_de": it.get("ex_de", ""),
                "dataset": it.get("dataset", "")
            })
    return mapped


@app.get("/learn")
async def learn(direction: str = "fr-de"):
    return transform_direction(direction, VOCAB)


@app.get("/test")
async def test(direction: str = "fr-de", exclude: Optional[str] = None):
    if direction not in {"fr-de", "de-fr"}:
        raise HTTPException(status_code=400, detail="Invalid direction. Use fr-de or de-fr")

    # Filter out known
    unknown = [it for it in VOCAB if (it["fr"], it["de"]) not in KNOWN]
    # Further filter excluded numbers if provided
    if exclude:
        try:
            ex_nums = set(int(x) for x in re.split(r"[,\s]+", exclude.strip()) if x)
        except Exception:
            ex_nums = set()
        if ex_nums:
            unknown = [it for it in unknown if it.get("num") not in ex_nums]
    if not unknown:
        raise HTTPException(status_code=404, detail="Keine weiteren Wörter für diesen Test. Markieren Sie einige als bekannt oder starten Sie die Sitzung neu.")

    choice = random.choice(unknown)
    if direction == "fr-de":
        payload = {
            "question": choice["fr"],
            "answer": choice["de"],
            "pron": choice.get("pron", ""),
            "fr": choice["fr"],
            "de": choice["de"],
            "num": choice.get("num"),
            "pos": choice.get("pos", ""),
            "pp": choice.get("pp", ""),
            "ex_la": choice.get("ex_la", ""),
            "ex_de": choice.get("ex_de", ""),
            "dataset": choice.get("dataset", "")
        }
    else:
        payload = {
            "question": choice["de"],
            "answer": choice["fr"],
            "pron": choice.get("pron", ""),
            "fr": choice["fr"],
            "de": choice["de"],
            "num": choice.get("num"),
            "pos": choice.get("pos", ""),
            "pp": choice.get("pp", ""),
            "ex_la": choice.get("ex_la", ""),
            "ex_de": choice.get("ex_de", ""),
            "dataset": choice.get("dataset", "")
        }
    return payload


@app.post("/mark_known")
async def mark_known(body: KnownBody):
    global KNOWN
    KNOWN.add((body.fr, body.de))
    save_known(KNOWN)
    return {"status": "ok"}


@app.post("/reset_known")
async def reset_known():
    global KNOWN
    KNOWN = set()
    save_known(KNOWN)
    return {"status": "reset"}


# Optional utility endpoint to see known items
@app.get("/known")
async def get_known():
    return [{"fr": fr, "de": de} for fr, de in sorted(list(KNOWN))]


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)