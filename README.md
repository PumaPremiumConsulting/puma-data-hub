# Puma Lead Hub
Applicazione per ricevere i form dei clienti dai due siti e salvare:
- dati principali lead (nome, email, telefono, azienda, messaggio)
- **tutte le risposte del form** (anche radio/select/checkbox/preimpostate)

Domini autorizzati:
- `pumapremiumconsulting.com`
- `assessment-pumapremiumconsulting.com`

## Struttura database
Tabella `form_submissions`
- `source_site`
- `form_name`
- `full_name`
- `email`
- `phone`
- `company`
- `message`
- `submitted_at`
- `raw_payload` (payload completo della submission)

Tabella `form_answers`
- `submission_id`
- `source_site`
- `question_key`
- `answer_value`
- `position`

Ogni submission genera più righe in `form_answers`: una per ciascuna risposta.

## Avvio
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 3030
```

Apri `http://127.0.0.1:3030`.

## Deploy su Netlify (frontend + backend API)
Il progetto è configurato per:
- dashboard statica pubblicata da `static/`
- proxy API via redirect `/api/*` verso backend esterno (Render o Railway)

Endpoint pubblico API dopo il deploy:
- `https://<tuo-sito>.netlify.app/api/leads`
- `https://<tuo-sito>.netlify.app/api/leads?limit=100`
- `https://<tuo-sito>.netlify.app/api/lead-summary`

Passi rapidi:
1. Pusha il repository su GitHub.
2. Su Netlify fai **Add new site** e collega il repo.
3. Apri `netlify.toml` e sostituisci la riga proxy:
   - da `https://your-backend.onrender.com/api/:splat`
   - a:
     - `https://<tuo-backend>.onrender.com/api/:splat` (Render) oppure
     - `https://<tuo-backend>.up.railway.app/api/:splat` (Railway)
4. Assicurati che il backend esterno sia online e raggiungibile in HTTPS.
5. Deploy.

## Nota importante sul database
Quando usi Netlify come frontend + proxy, la variabile `DATABASE_URL` va impostata nel backend esterno (Render o Railway), non su Netlify frontend.
Conclusione pratica: in produzione usa sempre PostgreSQL persistente sul backend esterno.

## Endpoint
- `POST /api/leads` → salva submission
- `GET /api/leads?source_site=<dominio>` → elenco lead con array `answers`
- `GET /api/lead-summary` → riepilogo conteggi per sito
- `GET /api/sources` → domini consentiti

## Esempio payload con risposte preimpostate
```json
{
  "source_site": "assessment-pumapremiumconsulting.com",
  "form_name": "executive-assessment",
  "name": "Luca Bianchi",
  "email": "luca@azienda.it",
  "company": "Azienda SPA",
  "operational_tier": "Managed",
  "urgency": "Alta",
  "pain_points": ["Silos operativi", "Decisioni senza dati"],
  "message": "Vorrei un assessment completo"
}
```

In questo esempio, oltre ai campi lead, le chiavi `operational_tier`, `urgency`, `pain_points` vengono salvate in `form_answers`.
Il parser supporta anche payload assessment più complessi:
- array di oggetti domanda/risposta (`responses`, `answers`, `assessment_answers`)
- valori multiselezione (checkbox) come array
- JSON stringificato dentro un campo (es. `"{\"question\":\"...\",\"answer\":\"...\"}"`)
