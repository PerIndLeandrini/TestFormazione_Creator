import streamlit as st
import pandas as pd
from datetime import date, datetime
import random
import os
import glob
import hashlib
import io
import smtplib
import ssl
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email import encoders

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4, landscape

st.set_page_config(page_title="Quiz Formazione Sicurezza", page_icon="📝", layout="wide")

# ============================================================
# COSTANTI
# ============================================================
SOGLIA_SUPERAMENTO = 80.0
RISULTATI_CSV = "risultati_quiz.csv"

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


def build_quiz_pdf(
    nome: str,
    corso: str,
    argomento: str,
    data_quiz: date,
    punteggio: int,
    percentuale: float,
    superato: bool,
    quiz_df: pd.DataFrame,
    quiz_options,
    risposte_utente
) -> bytes:
    """Genera un PDF con riepilogo completo del quiz (domande, risposte date, correttezza)."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4

    y = height - 50

    titolo = "Report Quiz Formazione Sicurezza"
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, y, titolo)
    y -= 25

    c.setFont("Helvetica", 10)
    c.drawString(50, y, f"Nome: {nome or '-'}")
    y -= 15
    c.drawString(50, y, f"Corso / Modulo: {corso or argomento or '-'}")
    y -= 15
    data_str = data_quiz.strftime("%d/%m/%Y") if isinstance(data_quiz, date) else str(data_quiz)
    c.drawString(50, y, f"Data quiz: {data_str}")
    y -= 15
    c.drawString(50, y, f"Punteggio: {punteggio} / {len(quiz_df)} ({percentuale}%)")
    y -= 15
    esito_txt = "SUPERATO" if superato else "NON SUPERATO"
    c.drawString(50, y, f"Esito: {esito_txt} (soglia {SOGLIA_SUPERAMENTO}%)")
    y -= 30

    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, "Dettaglio domande:")
    y -= 20
    c.setFont("Helvetica", 9)

    for i, row in quiz_df.iterrows():
        domanda = row["domanda"]
        options = quiz_options[i]
        scelta = risposte_utente[i]
        correct_idx = quiz_options[i].index(next(o for o in options if o[1] == options[[lab for lab, _ in options].index(o[0])][1])) if quiz_options[i] else None

        # individua testo risposta corretta
        corretta_label = str(row["corretta"]).strip().upper()
        testo_corretta = ""
        for lab, txt in options:
            if lab == corretta_label:
                testo_corretta = txt
                break

        if scelta is None:
            esito = "NON RISPOSTA"
        elif scelta == testo_corretta:
            esito = "CORRETTA"
        else:
            esito = "ERRATA"

        # gestione a capo e pagine
        blocco = [
            f"{i+1}. {domanda}",
            f"   Esito: {esito}",
            f"   Risposta data: {scelta if scelta else 'NON RISPOSTA'}",
            f"   Risposta corretta: {testo_corretta}"
        ]

        for line in blocco:
            if y < 80:
                c.showPage()
                y = height - 50
                c.setFont("Helvetica", 9)
            c.drawString(50, y, line)
            y -= 12

        y -= 8  # spazio fra domande

    c.showPage()
    c.save()
    pdf_bytes = buf.getvalue()
    buf.close()
    return pdf_bytes


def build_badge_pdf(nome: str, corso: str, data_quiz: date, percentuale: float) -> bytes:
    """Badge semplice di superamento (A4 orizzontale)."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=landscape(A4))
    width, height = landscape(A4)

    c.setFillColorRGB(0.94, 0.97, 0.99)
    c.rect(0, 0, width, height, fill=1, stroke=0)

    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica-Bold", 22)
    c.drawCentredString(width / 2, height - 70, "Badge superamento quiz")

    c.setFont("Helvetica", 14)
    c.drawCentredString(width / 2, height - 110, f"Nome: {nome or '-'}")
    c.drawCentredString(width / 2, height - 140, f"Corso: {corso or '-'}")

    data_str = data_quiz.strftime("%d/%m/%Y") if isinstance(data_quiz, date) else str(data_quiz)
    c.drawCentredString(width / 2, height - 170, f"Data quiz: {data_str}")
    c.drawCentredString(width / 2, height - 200, f"Punteggio: {percentuale}%")

    c.setFont("Helvetica-Oblique", 10)
    c.drawRightString(width - 40, 40, "Rilasciato automaticamente dal sistema quiz sicurezza")

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
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
            server.login(sender, password)
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

if not st.session_state.logged_in:
    st.warning("Accesso riservato. Effettua il login dalla sidebar per utilizzare il quiz.")
    st.stop()

# ============================================================
# CONFIGURAZIONE QUIZ
# ============================================================
with st.sidebar:
    st.header("Impostazioni quiz")

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
    email_partecipante = st.text_input("Email partecipante (facoltativa)")
    corso = st.text_input("Corso / Modulo (es. Formazione generale 4h)", value="")
    data_quiz = st.date_input("Data quiz", value=date.today())

    st.divider()
    n_domande = st.number_input("Numero domande da estrarre", min_value=10, max_value=50, value=30, step=1)
    seed = st.text_input("Seed casuale (facoltativo, per avere sempre lo stesso quiz)", value="")

# Lettura banca domande
try:
    df = pd.read_csv(selected_path)
except Exception as e:
    st.error(f"Errore nella lettura del CSV '{selected_path}': {e}")
    st.stop()

required_cols = {"argomento", "codice", "domanda", "opzione_a", "opzione_b", "opzione_c", "opzione_d", "corretta"}
if not required_cols.issubset(set(df.columns)):
    st.error(f"Il CSV deve contenere almeno queste colonne: {', '.join(required_cols)}")
    st.stop()

argomenti = sorted(df["argomento"].dropna().unique().tolist())
argomento_scelto = st.selectbox("Seleziona l'argomento / modulo di formazione", options=argomenti)
df_topic = df[df["argomento"] == argomento_scelto].copy()

if df_topic.empty:
    st.warning("Nessuna domanda per l'argomento selezionato.")
    st.stop()

st.write(f"**Argomento selezionato:** {argomento_scelto} — Domande disponibili: {len(df_topic)}")

# Stato quiz
if "quiz_df" not in st.session_state:
    st.session_state.quiz_df = None
    st.session_state.quiz_options = None
    st.session_state.quiz_correct_idx = None

def prepara_quiz():
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
if st.button("✅ Correggi quiz"):
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
        st.success(f"Test SUPERATO ✅ (soglia {SOGLIA_SUPERAMENTO}%)")
    else:
        st.error(f"Test NON superato ❌ (soglia {SOGLIA_SUPERAMENTO}%)")

    st.markdown("---")

    if dettagli_errori:
        st.subheader("Domande errate / non risposte")
        df_err = pd.DataFrame(dettagli_errori)
        st.dataframe(df_err, use_container_width=True)
    else:
        st.success("Tutte le risposte sono corrette. Ottimo lavoro!")

    # PDF quiz
    pdf_quiz = build_quiz_pdf(
        nome=nome,
        corso=corso,
        argomento=argomento_scelto,
        data_quiz=data_quiz,
        punteggio=punteggio,
        percentuale=percentuale,
        superato=superato,
        quiz_df=quiz_df,
        quiz_options=quiz_options,
        risposte_utente=risposte_utente
    )

    nome_sanit = nome.replace(" ", "_") if nome else "partecipante"
    corso_sanit = (corso or argomento_scelto or "quiz").replace(" ", "_")
    data_str = data_quiz.strftime("%Y%m%d") if isinstance(data_quiz, date) else "data"
    base_filename = f"{data_str}_{corso_sanit}_{nome_sanit}"

    st.download_button(
        "⬇️ Scarica report quiz in PDF",
        data=pdf_quiz,
        file_name=f"{base_filename}_quiz.pdf",
        mime="application/pdf"
    )

    # Badge (solo se superato)
    badge_pdf = None
    if superato:
        badge_pdf = build_badge_pdf(
            nome=nome,
            corso=corso or argomento_scelto,
            data_quiz=data_quiz,
            percentuale=percentuale
        )
        st.download_button(
            "⬇️ Scarica badge PDF",
            data=badge_pdf,
            file_name=f"{base_filename}_badge.pdf",
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
        "data_quiz": data_quiz.strftime("%Y-%m-%d") if isinstance(data_quiz, date) else str(data_quiz),
        "n_domande": totale,
        "punteggio": punteggio,
        "percentuale": percentuale,
        "superato": superato,
        "seed": seed
    }
    salva_risultato_csv(riga_csv)

    # Email sempre, con dettaglio domande nel corpo + allegati
    oggetto_quiz = corso or argomento_scelto or "Quiz Sicurezza"
    subject = f"{nome or 'Partecipante'} - {oggetto_quiz} - Punteggio {percentuale}%"

    body_lines = [
        "Esito quiz formazione sicurezza.",
        "",
        f"Nome: {nome or '-'}",
        f"Corso / Modulo: {oggetto_quiz}",
        f"Data quiz: {data_quiz.strftime('%d/%m/%Y') if isinstance(data_quiz, date) else str(data_quiz)}",
        f"Punteggio: {punteggio} / {totale} ({percentuale}%)",
        f"Esito: {'SUPERATO' if superato else 'NON SUPERATO'} (soglia {SOGLIA_SUPERAMENTO}%)",
        "",
        "Dettaglio domande:",
        "-------------------",
    ]

    for d in storico_domande:
        body_lines.append(f"{d['N']}. {d['Domanda']}")
        body_lines.append(f"   Esito: {d['Esito']}")
        body_lines.append(f"   Risposta data: {d['Risposta data']}")
        body_lines.append("")

    body_lines.append("In allegato il report PDF del test.")
    if superato:
        body_lines.append("È allegato anche il badge di superamento in formato PDF.")

    body = "\n".join(body_lines)

    attachments = [
        (f"{base_filename}_quiz.pdf", pdf_quiz, "application/pdf")
    ]
    if superato and badge_pdf is not None:
        attachments.append((f"{base_filename}_badge.pdf", badge_pdf, "application/pdf"))

    extra_to = [email_partecipante] if email_partecipante else []
    send_email_with_attachments(subject, body, attachments, extra_to=extra_to)
