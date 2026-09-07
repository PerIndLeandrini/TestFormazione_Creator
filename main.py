import streamlit as st
import pandas as pd
from datetime import date, datetime
import random
import os
import hashlib
import io
import smtplib
import ssl
from pathlib import Path
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email import encoders

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4, landscape
from quiz_db import list_banks, list_topics, load_questions

st.set_page_config(page_title="Test finale Formazione Sicurezza", page_icon="📝", layout="wide")

# ============================================================
# COSTANTI
# ============================================================
SOGLIA_SUPERAMENTO = 80.0
RISULTATI_CSV = "risultati_test_finale.csv"
BASE_DIR = Path(__file__).resolve().parent
QUIZ_DB = BASE_DIR / "quiz_database.db"
TUTTI_GLI_ARGOMENTI = "Tutti gli argomenti"

# ============================================================
# CSS
# ============================================================
st.markdown("""
<style>
:root {
  --navy:#102a43;
  --navy-light:#1f4e79;
  --navy-hover:#173f63;
  --page:#f7f9fc;
  --panel:#f1f3f5;
  --panel-border:#d8dee6;
  --text:#243447;
  --muted:#66788a;
  --danger:#b42318;
  --danger-bg:#fee4e2;
}

/* Area principale */
[data-testid="stAppViewContainer"] { background:var(--page); color:var(--text); }
[data-testid="stHeader"] { background:rgba(247,249,252,.92); }
.block-container { padding-top:1.25rem; padding-bottom:3rem; max-width:1400px; }
h1,h2,h3 { color:var(--navy); letter-spacing:.15px; }
h1 { font-weight:750; }
p, label, .stMarkdown { color:var(--text); }
hr { border-color:#dfe5ec; }

/* Sidebar navy */
[data-testid="stSidebar"] {
  background:linear-gradient(180deg, #0b2239 0%, var(--navy) 55%, #153a5b 100%);
  border-right:1px solid #203f5e;
}
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3,
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] [data-testid="stCaptionContainer"],
[data-testid="stSidebar"] .stMarkdown { color:#f5f8fc !important; }
[data-testid="stSidebar"] hr { border-color:rgba(255,255,255,.18); }
[data-testid="stSidebar"] [data-baseweb="input"] > div,
[data-testid="stSidebar"] [data-baseweb="select"] > div {
  background:#ffffff;
  border-color:#c9d5e2;
  border-radius:8px;
}
[data-testid="stSidebar"] [data-baseweb="input"] input { color:#172b3f; }

/* Riquadri delle domande */
[data-testid="stVerticalBlockBorderWrapper"] {
  background:var(--panel);
  border:1px solid var(--panel-border) !important;
  border-radius:12px !important;
  box-shadow:0 1px 3px rgba(16,42,67,.06);
}
[data-testid="stVerticalBlockBorderWrapper"]:hover {
  border-color:#b8c5d3 !important;
  box-shadow:0 3px 10px rgba(16,42,67,.08);
}

/* Risposte */
div[role="radiogroup"] > label {
  padding:7px 11px;
  border:1px solid #d2d9e1;
  border-radius:8px;
  margin-right:6px;
  margin-bottom:6px;
  background:#ffffff;
  transition:border-color .15s ease, background-color .15s ease;
}
div[role="radiogroup"] > label:hover {
  border-color:var(--navy-light);
  background:#f5f8fb;
}

/* Pulsanti e indicatori */
.stButton > button,
.stDownloadButton > button {
  background:var(--navy-light);
  color:#ffffff;
  border:1px solid var(--navy-light);
  border-radius:8px;
  font-weight:650;
}
.stButton > button:hover,
.stDownloadButton > button:hover {
  background:var(--navy-hover);
  color:#ffffff;
  border-color:var(--navy-hover);
}
[data-testid="stMetric"] {
  background:#ffffff;
  border:1px solid var(--panel-border);
  border-radius:10px;
  padding:14px 18px;
}
[data-testid="stMetricValue"] { color:var(--navy-light); }
.badge-nc { background:var(--danger); color:#fff; padding:4px 8px; border-radius:999px; font-size:12px; font-weight:700; }
.ref { color:var(--muted); font-size:12px; }
</style>
""", unsafe_allow_html=True)

st.title("📝 Hub Formazione - Crea il tuo test finale")

# ============================================================
# FUNZIONI UTILI
# ============================================================

@st.cache_data
def get_quiz_banks(db_path: str, database_mtime: float):
    """Carica le banche attive; mtime invalida la cache quando cambia il DB."""
    del database_mtime
    return list_banks(db_path)


@st.cache_data
def get_quiz_topics(db_path: str, database_mtime: float, bank_id: int):
    del database_mtime
    return list_topics(db_path, bank_id)


@st.cache_data
def get_quiz_questions(
    db_path: str, database_mtime: float, bank_id: int, topic_id: int | None
):
    del database_mtime
    return load_questions(db_path, bank_id, topic_id)


@st.cache_data
def load_users():
    try:
        df_users = pd.read_csv("utenti_test_finale.csv")
    except FileNotFoundError:
        # fallback per compatibilità se il file si chiama ancora utenti_quiz.csv
        try:
            df_users = pd.read_csv("utenti_quiz.csv")
        except FileNotFoundError:
            st.error("File 'utenti_test_finale.csv' (o 'utenti_quiz.csv') non trovato. Crealo nella stessa cartella dell'app.")
            return pd.DataFrame()

    required_cols = {"username", "password"}
    if not required_cols.issubset(set(df_users.columns)):
        st.error("Il file utenti deve contenere almeno le colonne: username, password.")
        return pd.DataFrame()

    return df_users


def get_icon(esito: str) -> str:
    esito = esito.upper()
    if esito == "CORRETTA":
        return "✅"
    if esito == "ERRATA":
        return "❌"
    return "⚠️"


def build_test_pdf(
    nome: str,
    corso: str,
    argomento: str,
    data_test: date,
    punteggio: int,
    percentuale: float,
    superato: bool,
    quiz_df: pd.DataFrame,
    quiz_options,
    risposte_utente
) -> bytes:
    """Genera un PDF con riepilogo completo del test finale (domande, risposte date, correttezza)."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4

    y = height - 50

    titolo = "Report Test finale formazione sicurezza"
    c.setFont("Helvetica-Bold", 16)
    c.setFillColorRGB(0, 0, 0)
    c.drawString(50, y, titolo)
    y -= 25

    c.setFont("Helvetica", 10)
    data_str = data_test.strftime("%d/%m/%Y") if isinstance(data_test, date) else str(data_test)
    corso_o_argomento = corso or argomento or "-"
    esito_txt = "SUPERATO" if superato else "NON SUPERATO"

    c.drawString(50, y, f"Nome: {nome or '-'}")
    y -= 15
    c.drawString(50, y, f"Corso / Modulo: {corso_o_argomento}")
    y -= 15
    c.drawString(50, y, f"Data test finale: {data_str}")
    y -= 15
    c.drawString(50, y, f"Punteggio: {punteggio} / {len(quiz_df)} ({percentuale}%)")
    y -= 15
    c.drawString(50, y, f"Esito: {esito_txt} (soglia {SOGLIA_SUPERAMENTO}%)")
    y -= 30

    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, "Dettaglio domande test finale:")
    y -= 20
    c.setFont("Helvetica", 9)

    for i, row in quiz_df.iterrows():
        domanda = str(row["domanda"])
        options = quiz_options[i]
        scelta = risposte_utente[i]

        # individua testo risposta corretta
        corretta_label = str(row["corretta"]).strip().upper()
        testo_corretta = ""
        for lab, txt in options:
            if lab == corretta_label:
                testo_corretta = txt
                break

        # esito
        if scelta is None:
            esito = "NON RISPOSTA"
        elif scelta == testo_corretta:
            esito = "CORRETTA"
        else:
            esito = "ERRATA"

        icon = get_icon(esito)

        # nuova pagina se serve
        if y < 100:
            c.showPage()
            c.setFont("Helvetica", 9)
            y = height - 50

        # Domanda (nero)
        c.setFillColorRGB(0, 0, 0)
        c.drawString(50, y, f"{i+1}. {domanda}")
        y -= 12

        # Esito (colorato)
        if esito == "CORRETTA":
            c.setFillColorRGB(0.0, 0.5, 0.0)  # verde
        elif esito == "ERRATA":
            c.setFillColorRGB(0.75, 0.0, 0.0)  # rosso
        else:
            c.setFillColorRGB(0.8, 0.5, 0.0)   # arancio

        c.drawString(50, y, f"{icon} Esito: {esito}")
        y -= 12
        c.drawString(50, y, f"   Risposta data: {scelta if scelta else 'NON RISPOSTA'}")
        y -= 12

        # Risposta corretta (nero)
        c.setFillColorRGB(0, 0, 0)
        c.drawString(50, y, f"   Risposta corretta: {testo_corretta}")
        y -= 16  # piccolo spazio extra tra domande

    c.showPage()
    c.save()
    pdf_bytes = buf.getvalue()
    buf.close()
    return pdf_bytes


def build_badge_pdf(nome: str, corso: str, data_test: date, percentuale: float) -> bytes:
    """Badge semplice di superamento test finale (A4 orizzontale)."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=landscape(A4))
    width, height = landscape(A4)

    c.setFillColorRGB(0.94, 0.97, 0.99)
    c.rect(0, 0, width, height, fill=1, stroke=0)

    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica-Bold", 22)
    c.drawCentredString(width / 2, height - 70, "Badge superamento test finale")

    c.setFont("Helvetica", 14)
    c.drawCentredString(width / 2, height - 110, f"Nome: {nome or '-'}")
    c.drawCentredString(width / 2, height - 140, f"Corso: {corso or '-'}")

    data_str = data_test.strftime("%d/%m/%Y") if isinstance(data_test, date) else str(data_test)
    c.drawCentredString(width / 2, height - 170, f"Data test finale: {data_str}")
    c.drawCentredString(width / 2, height - 200, f"Punteggio: {percentuale}%")

    c.setFont("Helvetica-Oblique", 10)
    c.drawRightString(width - 40, 40, "Rilasciato automaticamente dal sistema di test finale sicurezza")

    c.showPage()
    c.save()
    pdf_bytes = buf.getvalue()
    buf.close()
    return pdf_bytes


def salva_risultato_csv(riga: dict, path: str = RISULTATI_CSV):
    df_row = pd.DataFrame([riga])
    if os.path.exists(path):
        try:
            df_old = pd.read_csv(path)
            df_new = pd.concat([df_old, df_row], ignore_index=True)
        except Exception:
            df_new = df_row
    else:
        df_new = df_row
    df_new.to_csv(path, index=False)


def send_email_with_attachments(subject: str, body: str, attachments, extra_to=None):
    """
    attachments: lista di tuple (filename, bytes_data, mime_type)
    extra_to: lista di destinatari aggiuntivi
    """
    try:
        email_conf = st.secrets["email"]
        sender = email_conf["sender"]
        receiver = email_conf["receiver"]
        st.write("Mittente:", sender)
        st.write("Destinatario principale:", receiver)
        password = email_conf["password"]
    except Exception:
        st.error("Configurazione email non trovata in st.secrets['email'].")
        return

    to_addrs = [receiver]
    if extra_to:
        to_addrs.extend([addr for addr in extra_to if addr])

    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = ", ".join(to_addrs)
    msg["Subject"] = subject

    msg.attach(MIMEText(body, "plain"))

    for filename, data_bytes, mime_type in attachments:
        maintype, subtype = mime_type.split("/", 1)
        part = MIMEBase(maintype, subtype)
        part.set_payload(data_bytes)
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f'attachment; filename="{filename}"')
        msg.attach(part)

    try:
      smtp_server = email_conf["smtp_server"]
      smtp_port = int(email_conf["smtp_port"])

      context = ssl.create_default_context()

      with smtplib.SMTP_SSL(
        smtp_server,
        smtp_port,
        context=context
      ) as server:
        server.login(sender, password)
        st.write("Destinatari:", to_addrs)
        server.sendmail(sender, to_addrs, msg.as_string())
        
      st.success("📧 Email inviata con successo.")
    except Exception as e:
        st.error(f"Errore nell'invio email: {e}")

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
            st.error("Nessun utente caricato. Verifica il file utenti.")
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

if not st.session_state.logged_in:
    st.warning("Accesso riservato. Effettua il login dalla sidebar a fianco.")
    st.stop()

# ============================================================
# CONFIGURAZIONE TEST FINALE
# ============================================================
with st.sidebar:
    st.header("SELEZIONARE BANCA DATI")

    if not QUIZ_DB.exists():
        st.error(
            "Database delle domande non trovato. "
            "Esegui 'python importa_quiz_csv.py' per crearlo."
        )
        st.stop()

    database_mtime = QUIZ_DB.stat().st_mtime
    quiz_banks = get_quiz_banks(str(QUIZ_DB), database_mtime)
    if not quiz_banks:
        st.error("Il database non contiene banche domande attive.")
        st.stop()

    bank_by_label = {
        f"{name} ({count} domande)": (bank_id, name)
        for bank_id, name, count in quiz_banks
    }
    selected_bank_label = st.selectbox("", options=list(bank_by_label))
    selected_bank_id, selected_label = bank_by_label[selected_bank_label]

    st.divider()
    st.header("Dati partecipante")
    nome = st.text_input("Nome e cognome")
    email_partecipante = st.text_input("Email partecipante (facoltativa)")
    corso = st.text_input("Corso / Modulo", value="")
    data_test = st.date_input("Data", value=date.today())

    st.divider()
    n_domande = st.number_input("Numero domande da estrarre", min_value=10, max_value=50, value=30, step=1)
    seed = st.text_input("Seed casuale (facoltativo, per avere sempre lo stesso test finale)", value="")

# Lettura banca e argomento dal database SQLite
try:
    topics = get_quiz_topics(str(QUIZ_DB), database_mtime, selected_bank_id)
    if not topics:
        st.error("La banca selezionata non contiene argomenti attivi.")
        st.stop()

    if len(topics) > 1:
        topic_by_label = {
            TUTTI_GLI_ARGOMENTI: (None, TUTTI_GLI_ARGOMENTI),
            **{
                f"{name} ({count})": (topic_id, name)
                for topic_id, name, count in topics
            },
        }
        selected_topic_label = st.selectbox(
            "Seleziona l'argomento / modulo di formazione",
            options=list(topic_by_label),
        )
        selected_topic_id, argomento_scelto = topic_by_label[selected_topic_label]
    else:
        selected_topic_id, argomento_scelto, _ = topics[0]
        st.selectbox(
            "Seleziona l'argomento / modulo di formazione",
            options=[argomento_scelto],
            disabled=True,
        )

    df_topic = get_quiz_questions(
        str(QUIZ_DB), database_mtime, selected_bank_id, selected_topic_id
    ).copy()
except Exception as e:
    st.error(f"Errore nella lettura del database delle domande: {e}")
    st.stop()

if df_topic.empty:
    st.warning("Nessuna domanda per l'argomento selezionato.")
    st.stop()

st.write(
    f"**Banca selezionata:** {selected_label} — "
    f"**Argomento:** {argomento_scelto} — "
    f"Domande disponibili: {len(df_topic)}"
)

# Stato test
if "quiz_df" not in st.session_state:
    st.session_state.quiz_df = None
    st.session_state.quiz_options = None
    st.session_state.quiz_correct_idx = None
if "quiz_source" not in st.session_state:
    st.session_state.quiz_source = None

current_quiz_source = (selected_bank_id, selected_topic_id)
if st.session_state.quiz_source != current_quiz_source:
    st.session_state.quiz_df = None
    st.session_state.quiz_options = None
    st.session_state.quiz_correct_idx = None
    for key in list(st.session_state):
        if key.startswith("q_"):
            del st.session_state[key]

def prepara_test():
    seed_str = seed.strip()
    seed_int = None
    if seed_str:
        seed_int = int(hashlib.sha256(seed_str.encode("utf-8")).hexdigest(), 16) % (2**32)

    n = min(n_domande, len(df_topic))
    if seed_int is not None:
        quiz_df = df_topic.sample(n=n, random_state=seed_int).reset_index(drop=True)
        random.seed(seed_int)
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
        random.shuffle(options)
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
    st.session_state.quiz_source = current_quiz_source

st.markdown("---")
if st.button('🎲'):
    prepara_test()

if st.session_state.quiz_df is None:
    st.info("Premi il bottone qui sopra a forma di dado **'Preparai il test finale (estraendo le domande dalla banca dati selezionata)'** Potrai svolgere il test subito dopo...")
    st.stop()

quiz_df = st.session_state.quiz_df
quiz_options = st.session_state.quiz_options
quiz_correct_idx = st.session_state.quiz_correct_idx

st.subheader(f"Test finale generato — {len(quiz_df)} domande")

# Visualizzazione domande
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

# ============================================================
# CORREZIONE + PDF + CSV + EMAIL
# ============================================================
if st.button("✅ Correggi test finale"):
    punteggio = 0
    totale = len(quiz_df)
    dettagli_errori = []
    storico_domande = []

    for i, row in quiz_df.iterrows():
        scelta = risposte_utente[i]
        options = quiz_options[i]
        correct_idx = quiz_correct_idx[i]

        if correct_idx is None:
            testo_corretta = ""
        else:
            testo_corretta = options[correct_idx][1]

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

        storico_domande.append({
            "N": i + 1,
            "Domanda": row["domanda"],
            "Esito": esito,
            "Risposta data": scelta if scelta else "NON RISPOSTA",
        })

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
    superato = percentuale >= SOGLIA_SUPERAMENTO

    col1, col2 = st.columns(2)
    with col1:
        st.metric("Risposte corrette", f"{punteggio} / {totale}")
    with col2:
        st.metric("Punteggio %", f"{percentuale}%")

    if superato:
        st.success(f"Test finale SUPERATO ✅ (soglia {SOGLIA_SUPERAMENTO}%)")
    else:
        st.error(f"Test finale NON superato ❌ (soglia {SOGLIA_SUPERAMENTO}%)")

    st.markdown("---")

    if dettagli_errori:
        st.subheader("Domande errate / non risposte")
        df_err = pd.DataFrame(dettagli_errori)
        st.dataframe(df_err, use_container_width=True)
    else:
        st.success("Tutte le risposte sono corrette. Ottimo lavoro!")

    # PDF test finale
    pdf_test = build_test_pdf(
        nome=nome,
        corso=corso,
        argomento=argomento_scelto,
        data_test=data_test,
        punteggio=punteggio,
        percentuale=percentuale,
        superato=superato,
        quiz_df=quiz_df,
        quiz_options=quiz_options,
        risposte_utente=risposte_utente
    )

    nome_sanit = nome.replace(" ", "_") if nome else "partecipante"
    corso_sanit = (corso or argomento_scelto or "test_finale").replace(" ", "_")
    data_str = data_test.strftime("%Y%m%d") if isinstance(data_test, date) else "data"
    base_filename = f"{data_str}_{corso_sanit}_{nome_sanit}"

    st.download_button(
        "⬇️ Scarica report test finale in PDF",
        data=pdf_test,
        file_name=f"{base_filename}_test_finale.pdf",
        mime="application/pdf"
    )

    # Badge (solo se superato)
    badge_pdf = None
    if superato:
        badge_pdf = build_badge_pdf(
            nome=nome,
            corso=corso or argomento_scelto,
            data_test=data_test,
            percentuale=percentuale
        )
        st.download_button(
            "⬇️ Scarica badge test finale (PDF)",
            data=badge_pdf,
            file_name=f"{base_filename}_badge_test_finale.pdf",
            mime="application/pdf"
        )

    # Salvataggio CSV audit trail
    riga_csv = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "login_user": st.session_state.logged_user,
        "user_ente": st.session_state.user_ente,
        "user_role": st.session_state.user_role,
        "nome_partecipante": nome,
        "email_partecipante": email_partecipante,
        "corso": corso,
        "argomento": argomento_scelto,
        "banca_domande": selected_label,
        "data_test": data_test.strftime("%Y-%m-%d") if isinstance(data_test, date) else str(data_test),
        "n_domande": totale,
        "punteggio": punteggio,
        "percentuale": percentuale,
        "superato": superato,
        "seed": seed
    }
    salva_risultato_csv(riga_csv)

    # Email sempre, con dettaglio domande nel corpo + allegati
    oggetto_test = corso or argomento_scelto or "Test finale sicurezza"
    subject = f"{nome or 'Partecipante'} - {oggetto_test} - Punteggio {percentuale}%"

    body_lines = [
        "Esito test finale di formazione sicurezza.",
        "",
        f"Nome: {nome or '-'}",
        f"Corso / Modulo: {oggetto_test}",
        f"Data test finale: {data_test.strftime('%d/%m/%Y') if isinstance(data_test, date) else str(data_test)}",
        f"Punteggio: {punteggio} / {totale} ({percentuale}%)",
        f"Esito: {'SUPERATO' if superato else 'NON SUPERATO'} (soglia {SOGLIA_SUPERAMENTO}%)",
        "",
        "Dettaglio domande:",
        "-------------------",
    ]

    for d in storico_domande:
        icon = get_icon(d["Esito"])
        body_lines.append(f"{icon} {d['N']}. {d['Domanda']}")
        body_lines.append(f"   Esito: {d['Esito']}")
        body_lines.append(f"   Risposta data: {d['Risposta data']}")
        body_lines.append("")

    body_lines.append("In allegato il report PDF del test finale.")
    if superato:
        body_lines.append("È allegato anche il badge di superamento in formato PDF.")

    body = "\n".join(body_lines)

    attachments = [
        (f"{base_filename}_test_finale.pdf", pdf_test, "application/pdf")
    ]
    if superato and badge_pdf is not None:
        attachments.append(
            (f"{base_filename}_badge_test_finale.pdf", badge_pdf, "application/pdf")
        )

    extra_to = [email_partecipante] if email_partecipante else []
    send_email_with_attachments(subject, body, attachments, extra_to=extra_to)
