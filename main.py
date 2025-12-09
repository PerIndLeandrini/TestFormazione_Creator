import streamlit as st
import pandas as pd
from datetime import date
import random
import os
import glob
import hashlib
import smtplib
from email.message import EmailMessage
from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm

st.set_page_config(page_title="Quiz Formazione Sicurezza", page_icon="📝", layout="wide")

# ============================================================
# CONFIG GENERALE
# ============================================================
SOGLIA_SUPERAMENTO = 80.0  # 80%

# --- EMAIL DA st.secrets ---
try:
    EMAIL_SENDER = st.secrets["email"]["sender"]
    EMAIL_RECEIVER_DEFAULT = st.secrets["email"]["receiver"]
    EMAIL_PASSWORD = st.secrets["email"]["password"]
    EMAIL_SMTP_SERVER = st.secrets["email"].get("smtp_server", "smtp.gmail.com")
    EMAIL_SMTP_PORT = int(st.secrets["email"].get("smtp_port", 465))
except Exception:
    EMAIL_SENDER = None
    EMAIL_RECEIVER_DEFAULT = None
    EMAIL_PASSWORD = None
    EMAIL_SMTP_SERVER = "smtp.gmail.com"
    EMAIL_SMTP_PORT = 465

# ============================================================
# CSS
# ============================================================
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
# FUNZIONI UTILI
# ============================================================

@st.cache_data
def list_quiz_files(base_folder: str = "banche_dati_quiz"):
    """Ritorna lista di (label, path_assoluto) per tutti i CSV nella cartella indicata."""
    pattern = os.path.join(base_folder, "*.csv")
    files = glob.glob(pattern)

    quiz_files = []
    for f in sorted(files):
        name = os.path.basename(f)
        label = os.path.splitext(name)[0]  # nome file senza .csv
        quiz_files.append((label, f))
    return quiz_files


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


def build_badge_pdf(nome, corso, data_quiz, punteggio, totale, percentuale, esito,
                    argomento_scelto, ente, username):
    """
    Crea un badge PDF semplice con i dati del quiz.
    Ritorna bytes del PDF.
    """
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4

    # Background semplice
    c.setFillColorRGB(0.95, 0.95, 0.95)
    c.rect(1.5*cm, 6*cm, width - 3*cm, 10*cm, fill=True, stroke=0)

    # Header
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(width / 2, height - 4*cm, "Badge Esito Quiz Formazione Sicurezza")

    # Box principale
    c.setFont("Helvetica", 11)
    y = height - 6*cm

    corso_txt = corso or argomento_scelto or "Corso / Quiz"
    data_str = data_quiz.strftime("%d/%m/%Y")

    lines = [
        f"Partecipante: {nome or '-'}",
        f"Corso / Modulo: {corso_txt}",
        f"Data quiz: {data_str}",
        f"Ente / Azienda: {ente or '-'}",
        f"Utente sistema: {username or '-'}",
        "",
        f"Esito: {esito}",
        f"Punteggio: {punteggio} / {totale} ({percentuale}%)",
        f"Soglia di superamento: {SOGLIA_SUPERAMENTO}%",
    ]

    for line in lines:
        c.drawString(3*cm, y, line)
        y -= 0.8*cm

    # Esito grande
    c.setFont("Helvetica-Bold", 22)
    if esito == "SUPERATO":
        c.setFillColorRGB(0, 0.5, 0)  # verde
    else:
        c.setFillColorRGB(0.7, 0, 0)  # rosso
    c.drawCentredString(width / 2, 7*cm, esito)

    # Footer
    c.setFillColorRGB(0.3, 0.3, 0.3)
    c.setFont("Helvetica", 9)
    c.drawCentredString(width / 2, 2*cm, "Generato automaticamente dal sistema quiz 4Step")

    c.showPage()
    c.save()

    pdf_bytes = buf.getvalue()
    buf.close()
    return pdf_bytes


def send_email_with_pdf(to_addrs, subject, body, pdf_bytes, pdf_filename):
    """
    Invia una mail con allegato PDF.
    Usa le credenziali/config da st.secrets.
    """
    if not (EMAIL_SENDER and EMAIL_PASSWORD and EMAIL_RECEIVER_DEFAULT):
        return False, "Configurazione email non completa in st.secrets."

    if isinstance(to_addrs, str):
        to_addrs = [to_addrs]

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = EMAIL_SENDER
    msg["To"] = ", ".join(to_addrs)
    msg.set_content(body)

    msg.add_attachment(
        pdf_bytes,
        maintype="application",
        subtype="pdf",
        filename=pdf_filename
    )

    try:
        with smtplib.SMTP_SSL(EMAIL_SMTP_SERVER, EMAIL_SMTP_PORT) as server:
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.send_message(msg)
        return True, None
    except Exception as e:
        return False, str(e)


# ============================================================
# LOGIN
# ============================================================
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
# APP QUIZ (solo sotto login)
# ============================================================

# ---------- Sidebar: config ----------
with st.sidebar:
    st.header("Impostazioni quiz")

    # 🔽 ELENCO BANCHE DOMANDE DAL REPO
    quiz_files = list_quiz_files("banche_dati_quiz")

    if not quiz_files:
        st.error("Nessuna banca domande trovata nella cartella 'banche_dati_quiz'.")
        st.stop()

    labels = [label for label, _ in quiz_files]
    selected_label = st.selectbox("Seleziona banca domande", options=labels)
    selected_path = dict(quiz_files)[selected_label]

    st.caption(f"File selezionato: `{selected_path}`")
    st.caption("Formato richiesto: argomento, codice, domanda, opzione_a, opzione_b, opzione_c, opzione_d, corretta, riferimento")

    st.divider()
    st.header("Dati partecipante")
    nome = st.text_input("Nome e cognome")
    corso = st.text_input("Corso / Modulo (es. Formazione generale 4h)", value="")
    data_quiz = st.date_input("Data quiz", value=date.today())
    email_partecipante = st.text_input("Email partecipante (facoltativa)")

    st.divider()
    n_domande = st.number_input("Numero domande da estrarre", min_value=10, max_value=50, value=30, step=1)
    seed = st.text_input("Seed casuale (facoltativo, per avere sempre lo stesso quiz)", value="")

# ---------- Lettura CSV dalla banca selezionata ----------
try:
    df = pd.read_csv(selected_path)
except Exception as e:
    st.error(f"Errore nella lettura del CSV '{selected_path}': {e}")
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
    seed_str = seed.strip()
    seed_int = None

    # Se l'utente ha inserito un seed, lo trasformiamo in intero stabile
    if seed_str:
        seed_int = int(hashlib.sha256(seed_str.encode("utf-8")).hexdigest(), 16) % (2**32)

    # campionamento domande: se ho un seed, lo uso come random_state
    n = min(n_domande, len(df_topic))
    if seed_int is not None:
        quiz_df = df_topic.sample(n=n, random_state=seed_int).reset_index(drop=True)
        random.seed(seed_int)  # rende deterministico anche lo shuffle delle opzioni
    else:
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
        random.shuffle(options)  # con random.seed(seed_int) lo shuffle è ripetibile

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
            esito_dom = "NON RISPOSTA"
            corretta = testo_corretta
        elif scelta == testo_corretta:
            punteggio += 1
            esito_dom = "CORRETTA"
            corretta = testo_corretta
        else:
            esito_dom = "ERRATA"
            corretta = testo_corretta

        if esito_dom != "CORRETTA":
            dettagli_errori.append({
                "N": i+1,
                "Codice": row["codice"],
                "Domanda": row["domanda"],
                "Esito": esito_dom,
                "Risposta data": scelta if scelta else "",
                "Risposta corretta": corretta,
                "Riferimento": row.get("riferimento", "")
            })

    percentuale = round((punteggio / totale) * 100, 1) if totale > 0 else 0.0
    esito = "SUPERATO" if percentuale >= SOGLIA_SUPERAMENTO else "NON SUPERATO"

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Risposte corrette", f"{punteggio} / {totale}")
    with col2:
        st.metric("Punteggio %", f"{percentuale}%")
    with col3:
        st.metric("Esito", esito)

    st.markdown(f"**Soglia di superamento:** {SOGLIA_SUPERAMENTO}%")

    st.markdown("---")

    if dettagli_errori:
        st.subheader("Domande errate / non risposte")
        df_err = pd.DataFrame(dettagli_errori)
        st.dataframe(df_err, use_container_width=True)
    else:
        st.success("Tutte le risposte sono corrette. Ottimo lavoro!")

    # ---------- Badge PDF + invio email ----------
    if esito == "SUPERATO":
        corso_txt = corso or argomento_scelto or selected_label
        ente = st.session_state.user_ente
        username = st.session_state.logged_user

        badge_pdf = build_badge_pdf(
            nome=nome,
            corso=corso_txt,
            data_quiz=data_quiz,
            punteggio=punteggio,
            totale=totale,
            percentuale=percentuale,
            esito=esito,
            argomento_scelto=argomento_scelto,
            ente=ente,
            username=username
        )

        data_str = data_quiz.strftime("%Y%m%d")
        safe_nome = (nome or "partecipante").replace(" ", "_")
        pdf_filename = f"badge_{safe_nome}_{data_str}.pdf"

        # Download diretto (comodo anche per test)
        st.download_button(
            "⬇️ Scarica badge PDF",
            data=badge_pdf,
            file_name=pdf_filename,
            mime="application/pdf"
        )

        # Destinatari: default + eventualmente partecipante
        destinatari = []
        if EMAIL_RECEIVER_DEFAULT:
            destinatari.append(EMAIL_RECEIVER_DEFAULT)
        if email_partecipante:
            destinatari.append(email_partecipante.strip())

        if destinatari:
            subject = f"{nome or 'Partecipante'} - {corso_txt} - {percentuale}% ({punteggio}/{totale})"
            body = (
                "Buongiorno,\n\n"
                "in allegato il badge di esito del quiz di formazione sulla sicurezza.\n\n"
                f"Dettagli:\n"
                f"- Partecipante: {nome or '-'}\n"
                f"- Corso / Modulo: {corso_txt}\n"
                f"- Data quiz: {data_quiz.strftime('%d/%m/%Y')}\n"
                f"- Esito: {esito}\n"
                f"- Punteggio: {punteggio}/{totale} ({percentuale}%)\n\n"
                "Email generata automaticamente dal sistema quiz 4Step."
            )

            ok, err = send_email_with_pdf(destinatari, subject, body, badge_pdf, pdf_filename)
            if ok:
                st.success(f"Badge PDF inviato via email a: {', '.join(destinatari)}")
            else:
                st.error(f"Errore nell'invio email: {err}")
        else:
            st.info("Badge generato, ma nessun destinatario email configurato.")
    else:
        st.warning("Punteggio inferiore alla soglia di superamento: il badge PDF non viene generato.")
