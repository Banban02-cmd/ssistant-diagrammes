import streamlit as st
from dataclasses import dataclass, field
from typing import List, Dict, Tuple

# ------------------------------
# Moteur d'aide (règles, pas d'IA externe)
# ------------------------------

@dataclass
class SessionState:
    step: int = 1
    hints_given: int = 0
    goal: str | None = None
    variable: str | None = None
    var_type: str | None = None  # "qualitative" | "quantitative_discrete"
    categories: List[str] = field(default_factory=list)
    counts: List[int] = field(default_factory=list)
    scale_choice: Dict[str, int] = field(default_factory=dict)  # {"step":..., "top":...}
    scale_justif: str | None = None
    checklist: Dict[str, bool] = field(default_factory=dict)
    improvement: str | None = None
    reflection: str | None = None

MAX_HINTS_PER_STEP = 1

BANNED_PHRASES = [
    "fais le graphique", "trace le graphique", "tracer", "donne le code",
    "code complet", "plot", "matplotlib", "ggplot", "fais-le à ma place",
]


def guardrails(text: str) -> str | None:
    lower = text.lower()
    if any(b in lower for b in BANNED_PHRASES):
        return (
            "Je ne peux pas produire le diagramme ni fournir du code de tracé. "
            "Je peux t'aider à le construire, étape par étape."
        )
    return None


def analyze_data(categories: List[str], counts: List[int]) -> Tuple[List[str], Dict[str, int]]:
    issues = []
    unique = [c.strip() for c in categories if str(c).strip() != ""]
    if len(set(map(lambda s: s.lower(), unique))) != len(unique):
        issues.append("Catégories en doublon ou variantes d'orthographe : harmonise la casse/accents.")
    try:
        ints = [int(x) for x in counts]
    except Exception:
        issues.append("Effectifs non entiers : assure-toi que chaque effectif est un entier.")
        ints = []

    if ints:
        if any(v < 0 for v in ints):
            issues.append("Effectifs négatifs détectés : vérifie la saisie.")
        total = sum(ints)
        if total == 0:
            issues.append("Somme nulle : vérifie que les effectifs ne sont pas vides ou tous nuls.")
        maxv = max(ints)
    else:
        total = 0
        maxv = 0

    # Suggestion d'échelle "ronde"
    suggested_step = max(1, round(maxv / 8)) if maxv else 1
    rounded_top = ((maxv // suggested_step) + 1) * suggested_step if maxv else 10

    return issues, {"total": total, "max": maxv, "suggested_step": suggested_step, "rounded_top": rounded_top}


def give_hint(state: SessionState, topic: str) -> str:
    if state.hints_given >= MAX_HINTS_PER_STEP:
        return "Teste d'abord ta propre idée, puis reviens avec ton choix justifié."
    state.hints_given += 1
    if topic == "scale":
        return (
            "Indice : vise ~8 à 12 graduations régulières sur l'axe vertical. "
            "Choisis un pas qui dépasse légèrement l'effectif max quand on multiplie par le nombre de graduations."
        )
    if topic == "labels":
        return (
            "Indice : un bon titre = [verbe d'action] + [variable] + [population] + [contexte/année]."
        )
    if topic == "data":
        return (
            "Indice : liste d'abord les catégories uniques, puis additionne les effectifs de catégories homonymes (casse/accents)."
        )
    return "Indice : vérifie la cohérence des totaux et l'uniformité des catégories."


def reset_hints():
    st.session_state.engine.hints_given = 0


# ------------------------------
# UI Streamlit
# ------------------------------

st.set_page_config(page_title="Assistant diagrammes en barres (sans IA externe)", layout="wide")

if "engine" not in st.session_state:
    st.session_state.engine = SessionState()

engine: SessionState = st.session_state.engine

st.title("🧭 Assistant diagrammes en barres — sans API IA")
st.caption(
    "Cet assistant guide l'élève pour concevoir **son propre** diagramme en barres. "
    "Il ne trace pas de graphique et ne fournit pas de code de tracé."
)

with st.sidebar:
    st.header("Mode enseignant")
    st.markdown(
        "- **Garde-fous** : l'assistant refuse de tracer à la place de l'élève.\n"
        "- **Aides graduées** : 1 indice maximum par étape.\n"
        "- **Production séparée** : l'élève trace ailleurs (papier, tableur, GeoGebra, Python...)."
    )
    if st.button("🔄 Réinitialiser le parcours"):
        st.session_state.engine = SessionState()
        st.rerun()

st.markdown(f"### Étape {engine.step} / 5")

# --------------- Étape 1 ---------------
if engine.step == 1:
    st.subheader("Cadrer la question d'étude")
    engine.goal = st.text_area(
        "En une phrase : quelle question ton diagramme doit-il éclairer ?",
        value=engine.goal or "",
        height=80,
        placeholder="Ex : Comparer les fruits préférés des élèves de 5e B"
    )

    col1, col2 = st.columns(2)
    with col1:
        engine.variable = st.text_input("Variable étudiée", value=engine.variable or "", placeholder="Ex : Fruit préféré")
    with col2:
        engine.var_type = st.radio(
            "Nature de la variable",
            options=["qualitative", "quantitative_discrete"],
            index=(0 if engine.var_type in [None, "qualitative"] else 1),
            horizontal=True,
        )

    user_free = st.text_input("Question libre à l'assistant (facultatif)")
    if user_free:
        gr = guardrails(user_free)
        st.info(gr or "Merci, concentre-toi sur la définition claire de la variable et de la population.")

    c1, c2, c3 = st.columns([1,1,1])
    if c1.button("💡 Un indice"):
        st.toast(give_hint(engine, "data"))
    if c2.button("✅ Valider l'étape", on_click=reset_hints):
        if not engine.goal or not engine.variable:
            st.error("Merci de renseigner la question et la variable.")
        else:
            engine.step = 2
            st.rerun()
    c3.write("")

# --------------- Étape 2 ---------------
elif engine.step == 2:
    st.subheader("Préparer les données : catégories et effectifs")
    st.markdown("Saisis tes catégories et effectifs. L'outil contrôle la cohérence, sans tracer.")

    st.write("**Table de saisie (modifie/ajoute des lignes)**")
    data = st.data_editor(
        [{"Catégorie": c if i < len(engine.categories) else "",
          "Effectif": engine.counts[i] if i < len(engine.counts) else 0}
         for i, c in enumerate(engine.categories + [""] * max(0, 5 - len(engine.categories)))],
        num_rows="dynamic",
        use_container_width=True,
        key="data_table",
    )

    # Extraction des colonnes
    cats = []
    counts = []
    for row in data:
        c = str(row.get("Catégorie", "")).strip()
        v = row.get("Effectif", 0)
        if c == "" and (v == 0 or v == ""):
            continue
        cats.append(c)
        try:
            counts.append(int(v))
        except Exception:
            counts.append(v)  # laisser tel quel pour le validateur

    engine.categories = cats
    engine.counts = counts

    issues, stats = analyze_data(engine.categories, engine.counts)

    colA, colB, colC = st.columns(3)
    colA.metric("Nombre de catégories", len(engine.categories))
    colB.metric("Somme des effectifs", stats.get("total", 0))
    colC.metric("Effectif maximum", stats.get("max", 0))

    if issues:
        st.warning("\n".join([f"• {msg}" for msg in issues]))
    else:
        st.success("Données cohérentes au premier regard.")

    c1, c2, c3 = st.columns([1,1,1])
    if c1.button("💡 Un indice"):
        st.toast(give_hint(engine, "data"))
    if c2.button("✅ Valider l'étape", on_click=reset_hints):
        if len(engine.categories) < 2 or len(engine.categories) != len(engine.counts):
            st.error("Il faut au moins 2 catégories et un effectif par catégorie.")
        else:
            engine.step = 3
            st.rerun()

# --------------- Étape 3 ---------------
elif engine.step == 3:
    st.subheader("Choisir l'échelle de l'axe vertical")
    issues, stats = analyze_data(engine.categories, engine.counts)
    st.markdown(
        f"Effectif max détecté : **{stats.get('max', 0)}**  ·  Suggestion de pas : **{stats.get('suggested_step', 1)}**  ·  Sommet arrondi conseillé : **{stats.get('rounded_top', 10)}**"
    )

    col1, col2 = st.columns(2)
    with col1:
        step_val = st.number_input("Pas entre graduations (entier positif)", min_value=1, value=int(stats.get("suggested_step", 1)))
    with col2:
        top_val = st.number_input("Sommet de l'axe (entier > max)", min_value=max(1, stats.get("max", 0) + 1), value=int(stats.get("rounded_top", 10)))

    engine.scale_choice = {"step": int(step_val), "top": int(top_val)}
    engine.scale_justif = st.text_area("Justifie ton choix d'échelle en 2-3 phrases", value=engine.scale_justif or "")

    c1, c2, c3 = st.columns([1,1,1])
    if c1.button("💡 Un indice"):
        st.toast(give_hint(engine, "scale"))
    if c2.button("✅ Valider l'étape", on_click=reset_hints):
        if not engine.scale_justif or engine.scale_choice.get("top", 0) <= stats.get("max", 0):
            st.error("Écris une justification et vérifie que le sommet dépasse l'effectif max.")
        else:
            engine.step = 4
            st.rerun()

# --------------- Étape 4 ---------------
elif engine.step == 4:
    st.subheader("Auto-contrôle (checklist)")
    st.markdown("Coche ce qui est prêt pour ton diagramme (que tu traceras toi-même).")
    items = {
        "title": "Titre clair et informatif",
        "x": "Axe des catégories correctement libellé",
        "y": "Axe des effectifs avec unité",
        "bars": "Barres de largeur uniforme et espacements réguliers",
        "scale": "Échelle régulière et adaptée",
        "source": "Source des données indiquée",
        "legend": "Légende si nécessaire",
    }

    for key, label in items.items():
        engine.checklist[key] = st.checkbox(label, value=engine.checklist.get(key, False))

    engine.improvement = st.text_input(
        "Quel est **le** point prioritaire que tu amélioreras ?",
        value=engine.improvement or ""
    )

    c1, c2, c3 = st.columns([1,1,1])
    if c1.button("💡 Un indice"):
        st.toast(give_hint(engine, "labels"))
    if c2.button("✅ Valider l'étape", on_click=reset_hints):
        if not any(engine.checklist.values()):
            st.error("Coche au moins un élément prêt.")
        else:
            engine.step = 5
            st.rerun()

# --------------- Étape 5 ---------------
elif engine.step == 5:
    st.subheader("Bilan et export du rapport")
    engine.reflection = st.text_area(
        "Explique en 2-4 phrases comment ton diagramme répondra à la question de départ",
        value=engine.reflection or "",
        height=120,
    )

    # Génération d'un petit rapport texte (à rendre dans Moodle avec l'image du diagramme)
    report_lines = [
        "# Rapport d'auto-contrôle — Diagramme en barres",
        "",
        f"Question d'étude : {engine.goal}",
        f"Variable : {engine.variable}  ·  Nature : {engine.var_type}",
        "",
        "Catégories et effectifs :",
    ]
    for c, v in zip(engine.categories, engine.counts):
        report_lines.append(f"- {c} : {v}")

    report_lines += [
        "",
        f"Échelle choisie : pas = {engine.scale_choice.get('step', '')}, sommet = {engine.scale_choice.get('top', '')}",
        f"Justification : {engine.scale_justif}",
        "",
        "Checklist :",
    ]
    for key, label in {
        "title": "Titre", "x": "Axe X", "y": "Axe Y", "bars": "Barres",
        "scale": "Échelle", "source": "Source", "legend": "Légende",
    }.items():
        report_lines.append(f"- {label} : {'OK' if engine.checklist.get(key) else 'À revoir'}")

    report_lines += [
        "",
        f"Amélioration prioritaire : {engine.improvement}",
        "",
        f"Réflexion finale : {engine.reflection}",
        "",
        "(Rappel : le graphique doit être tracé par l'élève dans l'outil de son choix.)",
    ]

    report = "\n".join(report_lines)
    st.download_button("📥 Télécharger le rapport (.txt)", report, file_name="rapport_diagramme_barres.txt")

    st.success("Bravo ! Tu peux maintenant tracer ton diagramme et déposer l'image + ce rapport dans Moodle.")

    if st.button("↩️ Revenir à l'étape 1"):
        st.session_state.engine = SessionState()
        st.rerun()

# ------------ Pied de page ------------
st.divider()
st.markdown(
    "**Intégration Moodle** : ajoute une *Ressource → URL* ou une *Page* contenant un `<iframe>` vers cette application.\n"
    "Astuce : exige dans le devoir Moodle le *rapport téléchargé* + *l'image du diagramme* (production séparée)."
)
