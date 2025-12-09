# ---------- Correzione ----------
if st.button("✅ Correggi quiz"):
    punteggio = 0
    totale = len(quiz_df)
    dettagli_errori = []

    # Per ricostruire anche l'esito completo da inserire in mail
    storico_domande = []  # lista di dict: N, domanda, esito, risposta_data

    for i, row in quiz_df.iterrows():
        scelta = risposte_utente[i]
        options = quiz_options[i]
        correct_idx = quiz_correct_idx[i]

        if correct_idx is None:
            # se qualcosa non torna nella banca dati, saltiamo la domanda
            esito = "NON VALUTABILE"
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

        # per lo storico completo (anche corrette)
        storico_domande.append({
            "N": i + 1,
            "Domanda": row["domanda"],
            "Esito": esito,
            "Risposta data": scelta if scelta else "NON RISPOSTA",
        })

        # per la tabella errori a video (solo non corrette)
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

    # ---------- PDF quiz (sempre) ----------
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
        risposte_utente=risposte_utente,
        dettagli_errori=dettagli_errori
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

    # ---------- Badge (solo se superato) ----------
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

    # ---------- Salvataggio CSV audit trail ----------
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

    # ---------- Invio email SEMPRE con copia del test ----------
    oggetto_quiz = corso or argomento_scelto or "Quiz Sicurezza"
    subject = f"{nome or 'Partecipante'} - {oggetto_quiz} - Punteggio {percentuale}%"

    # blocco riassunto iniziale
    body_lines = [
        f"Esito quiz formazione sicurezza.",
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

    # 🔎 dettaglio completo nel corpo mail, solo domanda + esito + risposta data
    for d in storico_domande:
        body_lines.append(f"{d['N']}. {d['Domanda']}")
        body_lines.append(f"   Esito: {d['Esito']}")
        body_lines.append(f"   Risposta data: {d['Risposta data']}")
        body_lines.append("")  # riga vuota tra le domande

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
