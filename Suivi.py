# cote_pokemon.py
# Installation :  pip install streamlit requests pandas
# Lancement    :  streamlit run cote_pokemon.py
import json
import datetime as dt
from pathlib import Path

import pandas as pd
import requests
import streamlit as st

API = "https://api.tcgdex.net/v2"
COLLECTION = Path("collection.json")   # cartes suivies
HISTORY = Path("historique.json")      # relevés de valeur totale

LANGS = {"Français": "fr", "Anglais": "en", "Japonais": "ja"}
VARIANTS = {"normal": "Normale", "reverse": "Reverse holo", "holo": "Holo",
            "firstEdition": "Édition 1", "wPromo": "Promo W"}
METRICS = {"Tendance (trend)": "trend", "Moyenne 30 j": "avg30",
           "Moyenne 7 j": "avg7", "Prix le plus bas": "low"}

# Coefficients appliqués au prix Cardmarket de référence (modifiables dans la barre latérale).
# Cardmarket ne publie pas de prix par état et aucune API gratuite ne donne les prix PSA :
# ce sont donc des estimations, pas des cotes de marché.
COND_COEF = {"Mint (MT)": 1.15, "Near Mint (NM)": 1.0, "Excellent (EX)": 0.80,
             "Good (GD)": 0.60, "Light Played (LP)": 0.45, "Played (PL)": 0.30,
             "Poor (PO)": 0.15}
PSA_COEF = {10: 5.0, 9: 2.4, 8: 1.5, 7: 1.1, 6: 0.9, 5: 0.75, 4: 0.6, 3: 0.5, 2: 0.4, 1: 0.3}


# ---------- Accès API ----------
@st.cache_data(ttl=3600, show_spinner=False)
def api(path):
    r = requests.get(f"{API}/{path}", timeout=20)
    r.raise_for_status()
    return r.json()


@st.cache_data(ttl=86400, show_spinner=False)
def fetch_bytes(url):
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    return r.content


def show_image(urls, width):
    """Télécharge l'image côté Python (plus fiable que st.image(url)) et essaie plusieurs URL."""
    err = "aucune URL"
    for u in urls:
        if not u:
            continue
        try:
            st.image(fetch_bytes(u), width=width)
            return
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
    st.caption(f"Image indisponible ({err})")


def card_urls(base, quality="high"):
    """Images de cartes : URL + /qualité.format"""
    return [f"{base}/{quality}.webp", f"{base}/{quality}.png"] if base else []


def logo_urls(base):
    """Logos de séries : URL + .png (sans qualité)"""
    return [f"{base}.png", f"{base}.webp"] if base else []


def base_price(card, variant, metric):
    """Prix Cardmarket (EUR). Les variantes holo/reverse utilisent les champs '-holo'."""
    cm = (card.get("pricing") or {}).get("cardmarket") or {}
    foil = variant in ("holo", "reverse")
    keys = [f"{metric}-holo", metric] if foil else [metric, f"{metric}-holo"]
    for k in keys:
        if cm.get(k) is not None:
            return float(cm[k]), cm.get("updated")
    return None, None


def coef(kind, state):
    return PSA_COEF[int(state)] if kind == "psa" else COND_COEF[state]


def load(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


# ---------- Interface ----------
st.set_page_config(page_title="Suivi de côte Pokémon", page_icon="🃏", layout="wide")
st.title("🃏 Suivi de côte Pokémon")

with st.sidebar:
    st.header("Réglages")
    metric_label = st.selectbox("Prix Cardmarket utilisé", list(METRICS))
    metric = METRICS[metric_label]
    with st.expander("Coefficients d’état (modifiables)"):
        for k in COND_COEF:
            COND_COEF[k] = st.number_input(k, 0.0, 10.0, COND_COEF[k], 0.05, key=f"c_{k}")
    with st.expander("Coefficients PSA (estimations)"):
        for g in PSA_COEF:
            PSA_COEF[g] = st.number_input(f"PSA {g}", 0.0, 100.0, PSA_COEF[g], 0.1, key=f"p_{g}")

# 1) Langue
lang_label = st.radio("1 · Langue", list(LANGS), horizontal=True)
lang = LANGS[lang_label]

# 2) Série / extension
try:
    sets = api(f"{lang}/sets")
except Exception as e:
    st.error(f"Impossible de joindre TCGdex : {e}")
    st.stop()

sets = sorted(sets, key=lambda s: s["id"])[::-1]
set_brief = st.selectbox("2 · Série", sets, format_func=lambda s: f'{s["name"]} ({s["id"]})')
if set_brief is None:
    st.stop()

try:
    set_full = api(f'{lang}/sets/{set_brief["id"]}')
except Exception as e:
    st.error(f"Impossible de charger cette série : {e}")
    st.stop()

if set_full.get("logo"):
    show_image(logo_urls(set_full["logo"]), width=180)

# 3) Carte
cards = set_full.get("cards", [])
if not cards:
    st.warning("Aucune carte dans cette série.")
    st.stop()

brief = st.selectbox("3 · Carte", cards, format_func=lambda c: f'{c["localId"]} – {c["name"]}')

try:
    card = api(f'{lang}/cards/{brief["id"]}')
except Exception as e:
    st.error(f"Impossible de charger cette carte : {e}")
    st.stop()

left, right = st.columns([2, 1])
with right:
    if card.get("image"):
        show_image(card_urls(card["image"]), width=300)
    else:
        st.info("Pas d’image disponible pour cette carte.")

with left:
    # 4) Version (uniquement s'il y en a plusieurs)
    avail = [k for k in VARIANTS if (card.get("variants") or {}).get(k)] or ["normal"]
    if len(avail) > 1:
        variant = st.radio("4 · Version", avail, format_func=VARIANTS.get, horizontal=True)
    else:
        variant = avail[0]
        st.caption(f"Version unique : {VARIANTS[variant]}")
    if variant == "firstEdition":
        st.caption("⚠️ Cardmarket ne distingue pas l’Édition 1 dans ces données : prix de la version standard.")

    # 5) État
    kind_label = st.radio("5 · État", ["Carte raw", "Carte gradée (PSA)"], horizontal=True)
    if kind_label == "Carte raw":
        kind, state = "raw", st.selectbox("État Cardmarket", list(COND_COEF), index=1)
    else:
        kind, state = "psa", st.selectbox("Note PSA", list(PSA_COEF)[::-1], index=1)

    base, updated = base_price(card, variant, metric)
    if base is None:
        st.warning("Pas de prix Cardmarket pour cette carte : saisis un prix de référence.")
    ref = st.number_input("Prix de référence NM (€)", 0.0, 1000000.0, float(base or 0.0), 0.5,
                          key=f'ref_{card["id"]}_{variant}_{metric}')
    cote = ref * coef(kind, state)
    st.metric("Côte estimée", f"{cote:,.2f} €".replace(",", " "))
    if updated:
        st.caption(f"Prix Cardmarket mis à jour le {str(updated)[:10]}")
    if kind == "psa":
        st.caption("Les prix PSA sont estimés à partir du prix Cardmarket et des coefficients de la barre latérale.")

    qty = st.number_input("Quantité", 1, 999, 1)
    if st.button("➕ Ajouter au suivi", type="primary"):
        items = load(COLLECTION, [])
        items.append({"lang": lang, "card_id": card["id"], "name": card["name"],
                      "set": set_full["name"], "variant": variant, "kind": kind,
                      "state": str(state), "qty": int(qty),
                      "override": ref if base is None else None})
        save(COLLECTION, items)
        st.rerun()

# ---------- Collection suivie (prix rafraîchis en direct) ----------
st.divider()
st.subheader("Ma collection suivie")
items = load(COLLECTION, [])
if not items:
    st.info("Aucune carte suivie pour l’instant.")
else:
    rows = []
    for it in items:
        try:
            c = api(f'{it["lang"]}/cards/{it["card_id"]}')
            b, _ = base_price(c, it["variant"], metric)
        except Exception:
            c, b = {}, None
        if it.get("override") is not None:
            b = it["override"]
        st_val = it["state"] if it["kind"] == "raw" else int(it["state"])
        unit = None if b is None else b * coef(it["kind"], st_val)
        rows.append({"Image": f'{c["image"]}/low.webp' if c.get("image") else None,
                     "Carte": it["name"], "Série": it["set"],
                     "Langue": it["lang"].upper(),
                     "Version": VARIANTS.get(it["variant"], it["variant"]),
                     "État": ("PSA " if it["kind"] == "psa" else "") + it["state"],
                     "Qté": it["qty"],
                     "Côte unitaire (€)": None if unit is None else round(unit, 2),
                     "Total (€)": None if unit is None else round(unit * it["qty"], 2)})
    df = pd.DataFrame(rows)
    st.dataframe(df, hide_index=True,
                 column_config={"Image": st.column_config.ImageColumn("Image")})
    total = float(df["Total (€)"].sum())
    st.metric("Valeur totale", f"{total:,.2f} €".replace(",", " "))

    c1, c2 = st.columns(2)
    with c1:
        idx = st.selectbox("Supprimer une ligne", range(len(items)),
                           format_func=lambda i: f'{i + 1} – {items[i]["name"]} ({items[i]["state"]})')
        if st.button("🗑️ Supprimer"):
            items.pop(idx)
            save(COLLECTION, items)
            st.rerun()
    with c2:
        st.write("")
        if st.button("📸 Enregistrer un relevé de la valeur"):
            hist = load(HISTORY, [])
            hist.append({"date": dt.datetime.now().isoformat(timespec="minutes"), "total": round(total, 2)})
            save(HISTORY, hist)
            st.rerun()

    hist = load(HISTORY, [])
    if len(hist) > 1:
        h = pd.DataFrame(hist).set_index("date")
        st.line_chart(h["total"])