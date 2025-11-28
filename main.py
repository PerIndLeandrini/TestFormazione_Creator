import streamlit as st
import pandas as pd
from datetime import date
import random

st.set_page_config(page_title="Quiz Formazione Sicurezza", page_icon="📝", layout="wide")

# ---------- CSS ----------
st.markdown("""
<style>
:root { --brand:#0f766e; --muted:#6b7280; --soft:#e5e7eb; --danger:#b91c1c; --danger-bg:#fee2e2; }
.block-container { padding-top: 1rem; }
h1,h2,h3 { letter-spacing: .2px; }
div[role="radiogroup"] > label {
  padding: 6px 10px; border: 1px solid var(--soft); border-radius: 8px; margin-right: 6px; margin-bottom: 6px;
}
[data-testid="stMetricValue"] { color: var(--brand); }
.badge-nc { background:#b91c1c; color:#fff; padding:4px 8px; border-radius:999px; font-size:12px; font-weight:700; }
.ref { color:#666; font-size:12px; font-size:12px; }
</style>
""", unsafe_allow_html=True)

st.title("📝 Quiz Formazione Sicurezza sul Lavoro")
         
# ============================================================
# 🔐 LOGIN DA CSV ESTERNO (utenti_quiz.csv)
# ============================================================

@st.cache_data
def load_users():
    try:
        df_users = pd.read_csv("utenti_quiz.csv")
    except FileNotFoundError:
        st.error("File 'utenti_quiz.csv' non trovato. Crealo nella stessa cartella dell'app.")
        return pd.DataFrame()

    required_cols = {"username", "password"}
    if not required_cols.issubset(set(df_users.columns)):
        st.error("Il file 'utenti_quiz.csv' deve contenere almeno le colonne: username, password.")
        return pd.DataFrame()

    return df_users

df_users = load_users()

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "logged_user" not in st.session_state:
    st.session_state.logged_user = None
if "user_role" not in st.session_state:
    st.session_state.user_role = None
if "user_ente" not in st.session_state:
    st.session_state.user_ente = None

with st.sidebar:
    st.header("Accesso riservato 🔐")
    login_user = st.text_input("Utente", key="login_user")
    login_pwd = st.text_input("Password", type="password", key="login_pwd")
    login_btn = st.button("Login")

    if login_btn:
        if df_users is None or df_users.empty:
            st.error("Nessun utente caricato. Verifica il file 'utenti_quiz.csv'.")
        else:
            row = df_users[df_users["username"] == login_user]
            if not row.empty and str(row.iloc[0]["password"]) == login_pwd:
                st.session_state.logged_in = True
                st.session_state.logged_user = login_user
                st.session_state.user_role = row.iloc[0].get("ruolo", "")
                st.session_state.user_ente = row.iloc[0].get("ente", "")
                st.success(f"Accesso effettuato come: {login_user}")
            else:
                st.session_state.logged_in = False
                st.session_state.logged_user = None
                st.session_state.user_role = None
                st.session_state.user_ente = None
                st.error("Credenziali non valide.")

    if st.session_state.logged_in:
        info = f"✅ Utente: **{st.session_state.logged_user}**"
        if st.session_state.user_role:
            info += f" — Ruolo: **{st.session_state.user_role}**"
        if st.session_state.user_ente:
            info += f" — Ente: **{st.session_state.user_ente}**"
        st.caption(info)

        if st.button("Logout"):
            st.session_state.logged_in = False
            st.session_state.logged_user = None
            st.session_state.user_role = None
            st.session_state.user_ente = None
            st.experimental_rerun()

# Se NON loggato → blocca qui
if not st.session_state.logged_in:
    st.warning("Accesso riservato. Effettua il login dalla sidebar per utilizzare il quiz.")
    st.stop()


# ============================================================
# Da qui in giù: APP QUIZ COME L'AVEVI GIÀ (solo sotto login)
# ============================================================

# ---------- Sidebar: config ----------
with st.sidebar:
    st.header("Impostazioni quiz")

    csv_file = st.file_uploader("Carica banca domande (CSV)", type=["csv"])
    st.caption("Colonne richieste: argomento, codice, domanda, opzione_a, opzione_b, opzione_c, opzione_d, corretta, riferimento")

    st.divider()
    st.header("Dati partecipante")
    nome = st.text_input("Nome e cognome")
    corso = st.text_input("Corso / Modulo (es. Formazione generale 4h)", value="")
    data_quiz = st.date_input("Data quiz", value=date.today())

    st.divider()
    n_domande = st.number_input("Numero domande da estrarre", min_value=10, max_value=50, value=30, step=1)
    seed = st.text_input("Seed casuale (facoltativo, per avere sempre lo stesso quiz)", value="")

if csv_file is None:
    st.info("Carica un file CSV con la banca domande per iniziare.")
    st.stop()

# ---------- Lettura CSV ----------
try:
    df = pd.read_csv(csv_file)
except Exception as e:
    st.error(f"Errore nella lettura del CSV: {e}")
    st.stop()

required_cols = {"argomento", "codice", "domanda", "opzione_a", "opzione_b", "opzione_c", "opzione_d", "corretta"}
if not required_cols.issubset(set(df.columns)):
    st.error(f"Il CSV deve contenere almeno queste colonne: {', '.join(required_cols)}")
    st.stop()

# Argomenti
argomenti = sorted(df["argomento"].dropna().unique().tolist())
argomento_scelto = st.selectbox("Seleziona l'argomento / modulo di formazione", options=argomenti)
df_topic = df[df["argomento"] == argomento_scelto].copy()

if df_topic.empty:
    st.warning("Nessuna domanda per l'argomento selezionato.")
    st.stop()

st.write(f"**Argomento selezionato:** {argomento_scelto} — Domande disponibili: {len(df_topic)}")

# ---------- Inizializzazione stato ----------
if "quiz_df" not in st.session_state:
    st.session_state.quiz_df = None
    st.session_state.quiz_options = None      # lista di liste di (label, testo)
    st.session_state.quiz_correct_idx = None  # lista di indici corretti

# ---------- Generazione quiz ----------
def prepara_quiz():
    # seed opzionale
    if seed.strip():
        try:
            random.seed(seed.strip())
        except Exception:
            pass

    # campionamento domande
    n = min(n_domande, len(df_topic))
    quiz_df = df_topic.sample(n=n, random_state=None).reset_index(drop=True)

    quiz_options = []
    quiz_correct_idx = []

    for _, row in quiz_df.iterrows():
        options = [
            ("A", row["opzione_a"]),
            ("B", row["opzione_b"]),
            ("C", row["opzione_c"]),
            ("D", row["opzione_d"]),
        ]
        random.shuffle(options)  # mescola l'ordine di visualizzazione

        # trova indice della corretta dopo shuffle
        corretta_label = str(row["corretta"]).strip().upper()
        correct_idx = next(
            (i for i, (lab, _) in enumerate(options) if lab == corretta_label),
            None
        )

        quiz_options.append(options)
        quiz_correct_idx.append(correct_idx)

    st.session_state.quiz_df = quiz_df
    st.session_state.quiz_options = quiz_options
    st.session_state.quiz_correct_idx = quiz_correct_idx

st.markdown("---")
if st.button("🎲 Prepara quiz (estrai domande)"):
    prepara_quiz()

if st.session_state.quiz_df is None:
    st.info("Premi **'Prepara quiz'** per generare il test.")
    st.stop()

quiz_df = st.session_state.quiz_df
quiz_options = st.session_state.quiz_options
quiz_correct_idx = st.session_state.quiz_correct_idx

st.subheader(f"Quiz generato — {len(quiz_df)} domande")

# ---------- Visualizzazione domande ----------
risposte_utente = []

for i, row in quiz_df.iterrows():
    domanda = row["domanda"]
    codice = row["codice"]
    riferimento = row["riferimento"] if "riferimento" in row and not pd.isna(row["riferimento"]) else ""
    options = quiz_options[i]

    with st.container(border=True):
        st.markdown(f"**{i+1}. {domanda}**")
        if riferimento:
            st.markdown(f"<span class='ref'>Rif.: {riferimento}</span>", unsafe_allow_html=True)

        opzioni_testo = [t for _, t in options]
        scelta = st.radio(
            "Seleziona una risposta:",
            options=opzioni_testo,
            key=f"q_{i}_{codice}",
            index=None
        )
        risposte_utente.append(scelta)

st.markdown("---")

# ---------- Correzione ----------
if st.button("✅ Correggi quiz"):
    punteggio = 0
    totale = len(quiz_df)
    dettagli_errori = []

    for i, row in quiz_df.iterrows():
        scelta = risposte_utente[i]
        options = quiz_options[i]
        correct_idx = quiz_correct_idx[i]

        if correct_idx is None:
            continue

        testo_corretta = options[correct_idx][1]  # testo risposta corretta

        if scelta is None:
            esito = "NON RISPOSTA"
            corretta = testo_corretta
        elif scelta == testo_corretta:
            punteggio += 1
            esito = "CORRETTA"
            corretta = testo_corretta
        else:
            esito = "ERRATA"
            corretta = testo_corretta

        if esito != "CORRETTA":
            dettagli_errori.append({
                "N": i+1,
                "Codice": row["codice"],
                "Domanda": row["domanda"],
                "Esito": esito,
                "Risposta data": scelta if scelta else "",
                "Risposta corretta": corretta,
                "Riferimento": row.get("riferimento", "")
            })

    percentuale = round((punteggio / totale) * 100, 1) if totale > 0 else 0.0

    col1, col2 = st.columns(2)
    with col1:
        st.metric("Risposte corrette", f"{punteggio} / {totale}")
    with col2:
        st.metric("Punteggio %", f"{percentuale}%")

    st.markdown("---")

    if dettagli_errori:
        st.subheader("Domande errate / non risposte")
        df_err = pd.DataFrame(dettagli_errori)
        st.dataframe(df_err, use_container_width=True)
    else:
        st.success("Tutte le risposte sono corrette. Ottimo lavoro!")

    # FUTURO: qui puoi decidere soglia di superamento, salvataggio CSV, generazione badge, ecc.
