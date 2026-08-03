# AGENT.md — Dashboard Dynamica Retail

## Obiettivo del progetto

Costruire una dashboard Streamlit per il cliente **Dynamica Retail**.

La dashboard deve mostrare ogni giorno l’andamento delle campagne dal **primo giorno del mese fino a ieri**.

Il cliente è uno solo.

Non serve multi-cliente.

Non serve Power BI.

Non usare Google Cloud Storage.

Non usare servizi che richiedono carta di credito.

## Strategia finale concordata

Il sistema deve funzionare così:

```text
Google Sheet = dati manuali aggiornati dall'agenzia
Google Ads API = speso automatico Google
Meta Marketing API = speso automatico Meta
Dynamics / CRM = lead effettive, in futuro
PC aziendale Windows = robot giornaliero
GitHub privato = scatola online dei file latest
Archivio locale PC = storico giornaliero
Streamlit Cloud = dashboard visibile al cliente
```

## Flusso completo

```text
La collega aggiorna Google Sheet
        ↓
PC aziendale ogni mattina esegue script Python
        ↓
Python legge Google Sheet
        ↓
Python prende speso Google Ads
        ↓
Python prende speso Meta Ads
        ↓
Python, in futuro, prende lead CRM da Dynamics
        ↓
Python genera report_data.csv
        ↓
Python genera Excel aggiornato
        ↓
Python salva una copia storica locale sul PC
        ↓
Python aggiorna i file latest nella repo GitHub privata
        ↓
PC aziendale fa commit e push su GitHub
        ↓
Streamlit Cloud legge i file latest dalla repo
        ↓
Cliente vede dashboard aggiornata tramite link protetto da password
```

## Scelta storage definitiva

Usare **GitHub privato** come storage online dei file latest e degli snapshot
mensili aggregati necessari al filtro storico.

Non usare Google Cloud Storage.

Non usare bucket cloud.

Non collegare carta di credito.

## Cosa va su GitHub

Committare solo i file necessari alla dashboard:

```text
data/report_data.csv
data/report_daily_metrics.csv
exports/report_dynamica_updated.xlsx
data/last_update.json
data/history/YYYY-MM/report_data.csv
data/history/YYYY-MM/report_daily_metrics.csv
data/history/YYYY-MM/last_update.json
```

I primi quattro sono i file latest. Le cartelle `data/history/YYYY-MM/` sono
snapshot mensili aggregati e congelati, necessari per il filtro storico.

## Cosa resta solo sul PC aziendale

Lo storico giornaliero resta sul PC aziendale.

Non va su GitHub.

Esempio:

```text
archive/
  2026-07-01/
    report_data.csv
    report_dynamica_updated.xlsx
    last_update.json
  2026-07-02/
    report_data.csv
    report_dynamica_updated.xlsx
    last_update.json
```

## Perché questa scelta

Questa scelta è la migliore perché:

* non richiede carta di credito;
* è semplice da capire;
* GitHub privato basta per salvare i file latest;
* Streamlit Cloud può leggere i file dalla repo;
* il PC aziendale fa da robot giornaliero;
* lo storico resta al sicuro sul PC;
* il cliente vede solo la dashboard, non i file interni.

## Regola importante

GitHub non deve diventare il magazzino storico giornaliero completo.

GitHub contiene i file latest e una sola copia aggregata congelata per ogni mese
completo.

Lo storico completo resta nella cartella `archive/` del PC aziendale.

## Decisioni funzionali definitive

### Cliente

Il cliente è uno solo:

```text
Dynamica Retail
```

Non implementare sistema multi-cliente.

### Periodo dati

Usare sempre:

```text
start_date = primo giorno del mese corrente
end_date = ieri
```

Esempio:

se oggi è 22 luglio, il periodo dati è:

```text
2026-07-01 → 2026-07-21
```

Non usare oggi come data finale.

### Dati manuali

I dati manuali vengono aggiornati dall’agenzia in un Google Sheet.

La dashboard non deve modificare direttamente i dati manuali nella prima versione.

Google Sheet è la fonte ufficiale per:

* funnel;
* piattaforma;
* canale;
* nome campagna;
* investimento media;
* percentuale investimento;
* CPP medio;
* stima pratiche;
* CPL target;
* stima lead;
* action/commento manuale;
* ID campagna Google;
* ID campagna Meta;
* chiave futura Dynamics;
* flag enabled.

### Google Ads

Google Ads fornisce solo dati automatici di delivery.

Usare principalmente:

* campaign_id;
* campaign_name;
* spend;
* clicks;
* impressions;
* conversions, solo come dato informativo.

Non usare conversioni Google Ads come lead effettive.

Le lead effettive devono arrivare solo dal CRM.

### Meta Ads

Meta fornisce solo dati automatici di delivery.

Usare principalmente:

* campaign_id;
* campaign_name;
* spend;
* clicks;
* impressions.

Non usare lead Meta come lead effettive.

Le lead effettive devono arrivare solo dal CRM.

### Dynamics / CRM

Dynamics non è ancora disponibile.

Implementare solo modulo predisposto e disattivabile.

Le lead effettive devono arrivare da Dynamics/CRM solo quando il cliente fornirà:

* autorizzazione;
* tenant ID;
* client ID;
* client secret;
* URL ambiente;
* nome tabella lead;
* nome campo campagna;
* regola di conteggio lead valide.

Fino ad allora:

```text
DYNAMICS_ENABLED=false
```

e le lead effettive restano vuote o manuali se presenti nel Google Sheet.

### Action

La colonna Action resta manuale.

Non generare action automatiche.

La dashboard può mostrare alert informativi, ma non deve modificare il campo Action.

## Stack tecnico

Usare Python.

Librerie principali:

```text
streamlit
pandas
plotly
openpyxl
python-dotenv
requests
google-ads
facebook-business
msal
gspread
google-auth
```

Non includere `google-cloud-storage`.

## Architettura progetto

```text
dynamica-dashboard/
  ├── AGENT.md
  ├── app.py
  ├── requirements.txt
  ├── README.md
  ├── .env.example
  ├── .gitignore
  ├── run_daily_update.bat
  ├── data/
  │   ├── report_data.csv
  │   ├── last_update.json
  │   └── raw/
  │       ├── google_sheet_raw.csv
  │       ├── google_ads_raw.csv
  │       ├── meta_ads_raw.csv
  │       └── dynamics_raw.csv
  ├── templates/
  │   └── Piano_Dynamica_AUTOMATIZZAZIONE.xlsx
  ├── exports/
  │   └── report_dynamica_updated.xlsx
  ├── archive/
  │   └── YYYY-MM-DD/
  ├── logs/
  │   └── daily_update.log
  └── src/
      ├── __init__.py
      ├── config.py
      ├── dates.py
      ├── google_sheets_client.py
      ├── google_ads_client.py
      ├── meta_ads_client.py
      ├── dynamics_client.py
      ├── build_report_data.py
      ├── update_excel.py
      ├── archive_outputs.py
      ├── publish_to_github.py
      └── utils.py
```

## File `.env.example`

Creare `.env.example` con queste aree:

```text
General
Dashboard
Google Sheet manual input
Google Ads
Meta Ads
Dynamics / Dataverse
GitHub publishing
Local archive
```

Variabili richieste:

```text
CLIENT_NAME
USE_YESTERDAY_AS_END_DATE
TIMEZONE

DASHBOARD_PASSWORD

GOOGLE_SHEET_ENABLED
GOOGLE_SHEET_ID
GOOGLE_SHEET_WORKSHEET_NAME
GOOGLE_SERVICE_ACCOUNT_JSON_PATH
GOOGLE_SHEET_REFRESH_SECONDS

GOOGLE_ADS_CUSTOMER_ID
GOOGLE_ADS_LOGIN_CUSTOMER_ID
GOOGLE_ADS_CONFIG_PATH

META_ACCESS_TOKEN
META_AD_ACCOUNT_ID

DYNAMICS_ENABLED
DYNAMICS_TENANT_ID
DYNAMICS_CLIENT_ID
DYNAMICS_CLIENT_SECRET
DYNAMICS_ENVIRONMENT_URL
DYNAMICS_LEAD_TABLE
DYNAMICS_CAMPAIGN_FIELD

GITHUB_PUBLISH_ENABLED
GITHUB_BRANCH
GITHUB_COMMIT_MESSAGE_PREFIX

LOCAL_ARCHIVE_ENABLED
LOCAL_ARCHIVE_DIR
```

## File `.gitignore`

Non committare mai:

```text
.env
google-ads.yaml
service_account_google_sheet.json
.streamlit/secrets.toml
__pycache__/
.venv/
*.pyc
logs/*.log
data/raw/*.csv
archive/
```

Nota importante:

Non ignorare questi file, perché servono a Streamlit:

```text
data/report_data.csv
data/report_daily_metrics.csv
data/last_update.json
exports/report_dynamica_updated.xlsx
```

## Google Sheet

Il Google Sheet deve avere worksheet:

```text
manual_inputs
```

Colonne richieste:

```text
excel_row
funnel
platform
channel
campaign_name
investimento_media
percentuale_investimento
cpp_medio
stima_pratiche
cpl_target
stima_lead
lead_effettive_manual
action
google_campaign_id
meta_campaign_id
dynamics_campaign_key
enabled
```

Regole:

* `enabled=true` indica righe attive;
* Google usa `google_campaign_id`;
* Meta usa `meta_campaign_id`;
* Dynamics userà `dynamics_campaign_key`;
* `campaign_name` serve per visualizzazione e fallback;
* `action` resta manuale;
* `lead_effettive_manual` può essere usato solo temporaneamente finché Dynamics non è attivo.

## Build report data

Il sistema deve generare:

```text
data/report_data.csv
```

Colonne minime:

```text
report_date
start_date
end_date
excel_row
funnel
platform
channel
campaign_name
investimento_media
percentuale_investimento
cpp_medio
stima_pratiche
cpl_target
stima_lead
stima_lead_giornaliere
stima_lead_progressiva
lead_effettive
delta_lead
stima_spending_progressiva
speso_effettivo
delta_speso
delta_delivery_pct
cpl_effettivo
delta_cpl
action
google_campaign_id
meta_campaign_id
dynamics_campaign_key
source_status
```

## Regole calcolo

Calcolare:

```text
days_in_month = numero giorni del mese corrente
elapsed_days = giorni dal primo del mese a end_date inclusi

stima_lead_giornaliere = stima_lead / days_in_month
stima_lead_progressiva = stima_lead_giornaliere * elapsed_days
stima_spending_progressiva = investimento_media / days_in_month * elapsed_days
delta_lead = lead_effettive - stima_lead_progressiva
delta_speso = speso_effettivo - stima_spending_progressiva
delta_delivery_pct = delta_speso / stima_spending_progressiva
cpl_effettivo = speso_effettivo / lead_effettive
delta_cpl = cpl_effettivo - cpl_target
```

Eccezione DEM:

```text
dem_days_in_month = giorni da lunedi a venerdi nel mese corrente
dem_elapsed_days = giorni da lunedi a venerdi tra start_date ed end_date inclusi
stima_spending_progressiva = investimento_media / dem_days_in_month * dem_elapsed_days
```

Per le DEM si escludono solo sabato e domenica. Le festivita infrasettimanali
restano incluse. La regola riguarda lo spending stimato, non le lead stimate o
lo speso effettivo.

Gestione divisioni:

* se `lead_effettive` è 0 o vuoto, `cpl_effettivo` resta vuoto;
* se `stima_spending_progressiva` è 0 o vuoto, `delta_delivery_pct` resta vuoto;
* se `cpl_target` è vuoto, `delta_cpl` resta vuoto.

## Excel export

Generare:

```text
exports/report_dynamica_updated.xlsx
```

Regole:

* usare template Excel;
* aggiornare solo righe presenti nel report;
* non sovrascrivere dati manuali;
* mantenere Action manuale;
* aggiornare speso effettivo;
* aggiornare lead effettive solo se disponibili;
* mantenere formule esistenti;
* salvare copia esportabile.

## Archivio locale

Dopo aver generato CSV ed Excel, creare una copia locale in:

```text
archive/YYYY-MM-DD/
```

Con dentro:

```text
report_data.csv
report_dynamica_updated.xlsx
last_update.json
```

Lo storico locale non va committato su GitHub.

## Pubblicazione GitHub

Dopo archivio locale, aggiornare i file latest e gli eventuali nuovi snapshot
mensili nella repo:

```text
data/report_data.csv
data/report_daily_metrics.csv
data/last_update.json
exports/report_dynamica_updated.xlsx
data/history/YYYY-MM/report_data.csv
data/history/YYYY-MM/report_daily_metrics.csv
data/history/YYYY-MM/last_update.json
```

Poi fare commit e push.

Regole:

* se non ci sono modifiche, non fallire;
* commit message leggibile;
* non committare raw data;
* non committare archive;
* non committare logs;
* non committare secrets.

## last_update.json

Il file `data/last_update.json` deve contenere:

```text
client
start_date
end_date
updated_at
status
error opzionale
```

Non deve contenere secrets.

## Dashboard Streamlit

La dashboard deve leggere i dati direttamente dai file presenti nella repo:

```text
data/report_data.csv
data/last_update.json
exports/report_dynamica_updated.xlsx
data/history/YYYY-MM/report_data.csv
data/history/YYYY-MM/report_daily_metrics.csv
data/history/YYYY-MM/last_update.json
```

Non deve leggere Google Cloud Storage.

Non deve leggere file locali del PC aziendale.

## Login dashboard

Per MVP usare password semplice.

Password da Streamlit secrets o variabile ambiente.

Regole:

* se password errata, non mostrare dati;
* non mostrare token;
* non mostrare stacktrace tecnici;
* mostrare messaggi semplici.

## KPI dashboard

Mostrare:

* Speso totale;
* Investimento media totale;
* Stima spending progressiva totale;
* Delta speso totale;
* Delta delivery %;
* Lead effettive totali;
* CPL medio effettivo.

## Filtri dashboard

Sidebar:

* funnel;
* platform;
* channel;
* campagna.

Il filtro data deve consentire intervalli liberi interni a un solo mese. I mesi
chiusi vengono letti dagli snapshot congelati; il mese corrente resta dal primo
giorno del mese fino a ieri.

## Tabella dashboard

Mostrare:

```text
Funnel
Platform
Channel
Campagna
Investimento Media
Stima Spending Progressiva
Speso Effettivo
Delta Speso
Lead Effettive
CPL Target
CPL Effettivo
Delta CPL
Action
```

## Grafici dashboard

Grafici richiesti:

* Speso effettivo vs stima spending progressiva per campagna;
* CPL effettivo vs CPL target per campagna;
* Speso per piattaforma.

## Alert dashboard

Mostrare alert informativi:

* campagne con speso sotto stima oltre 20%;
* campagne con CPL sopra target oltre 20%;
* campagne con speso ma zero lead;
* campagne senza speso.

Non modificare Action.

## Export dashboard

Aggiungere pulsanti:

```text
Scarica Excel aggiornato
Scarica CSV dati
```

## Scheduler Windows

Il PC aziendale sempre acceso è lo scheduler.

Usare Utilità di pianificazione Windows.

Il file `run_daily_update.bat` deve orchestrare:

1. generazione report data;
2. generazione Excel;
3. creazione archivio locale;
4. pubblicazione latest su GitHub.

Orario consigliato:

```text
07:00 ogni giorno
```

Impostazioni consigliate:

* esegui anche se utente non connesso;
* esegui con privilegi più elevati;
* conserva log;
* riavvia in caso di errore.

## Logging

Scrivere log in:

```text
logs/daily_update.log
```

Loggare:

* inizio processo;
* periodo dati;
* righe lette da Google Sheet;
* campagne Google estratte;
* campagne Meta estratte;
* stato Dynamics;
* CSV generato;
* Excel generato;
* archivio locale creato;
* push GitHub riuscito o fallito.

Non loggare token o secrets.

## Streamlit Cloud

Deploy consigliato:

```text
Streamlit Community Cloud
```

Regole:

* repo GitHub privata;
* Streamlit legge codice e file latest dalla repo;
* dashboard protetta da password;
* cliente accede solo dal link Streamlit;
* cliente non accede alla repo GitHub;
* cliente non accede al Google Sheet.

## Implementazione per fasi

1. Creare skeleton progetto.
2. Leggere Google Sheet.
3. Creare dashboard mock da CSV locale.
4. Collegare Google Ads.
5. Collegare Meta Ads.
6. Generare `report_data.csv`.
7. Generare Excel export.
8. Salvare archivio locale.
9. Pubblicare latest su GitHub.
10. Collegare Streamlit Cloud.
11. Configurare Task Scheduler Windows.
12. Lasciare Dynamics placeholder.
13. Collegare Dynamics solo quando disponibile.

## Criteri di successo

Il progetto è valido quando:

1. La collega aggiorna Google Sheet.
2. Il PC aziendale esegue lo script ogni giorno.
3. Il sistema calcola dati dal primo del mese a ieri.
4. Google Ads aggiorna lo speso tramite campaign_id.
5. Meta Ads aggiorna lo speso tramite campaign_id.
6. Le lead effettive non vengono prese da Google o Meta.
7. Dynamics è predisposto ma disattivato.
8. Il CSV finale viene creato correttamente.
9. L’Excel esportabile viene creato correttamente.
10. Lo storico viene salvato localmente sul PC.
11. I file latest vengono pushati su GitHub privato.
12. Streamlit legge i file latest dalla repo.
13. Il cliente accede con password.
14. Il cliente vede KPI, tabella, grafici e alert.
15. Il cliente può scaricare Excel e CSV.
16. Nessun secret è esposto.

## Frase guida

```text
Google Sheet è il quaderno manuale.
Il PC aziendale è il robot giornaliero.
GitHub privato è la scatola online latest.
Archivio locale è il magazzino storico.
Streamlit è la vetrina cliente.
```
