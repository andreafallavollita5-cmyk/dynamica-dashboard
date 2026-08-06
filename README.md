# Ads local export

## Aggiornamento speso dashboard

Questo comando legge in sola lettura Google Sheet, Google Ads e Meta Ads per il
periodo dal primo giorno del mese a ieri, quindi rigenera il CSV latest:

```powershell
.\.venv\Scripts\python.exe -m src.build_report_data
```

Lo speso viene associato prima tramite `google_campaign_id` o
`meta_campaign_id`; il nome è usato come fallback solo quando l'ID non è
presente. Conversioni Google e azioni/lead Meta non vengono richieste né usate
come lead effettive.

## Automazione giornaliera

La routine completa si avvia con:

```powershell
.\run_daily_update.bat
```

Ogni mattina usa Dynamics quando `DYNAMICS_ENABLED=true`; finché il flag resta
`false`, usa il file Excel CRM valido più recente presente in `data/input/`
(i file temporanei `~$` vengono ignorati). Aggiorna Google Sheet,
CSV, Excel e archivio, quindi pubblica su GitHub soltanto i quattro file latest.
Il giorno 1 elabora il mese precedente completo. Se una sola API Ads non è
disponibile, mantiene l'ultimo valore valido dello stesso mese e segnala
l'aggiornamento parziale; se falliscono entrambe, i latest restano invariati.

Per installare o aggiornare l'attività Windows delle 07:00, aprire PowerShell
come amministratore ed eseguire:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_daily_task.ps1
```

Windows richiede la password dell'account in una finestra protetta; la password
non viene scritta nei file. L'attività recupera gli avvii saltati, può riattivare
il PC e ritenta tre volte in caso di errore.

## Dynamics 365 / Dataverse

L'integrazione usa in sola lettura la system view **LEAD QUESTO MESE PULITE**
(`13950fd2-5fae-ef11-b8e9-000d3a2aa135`). I filtri della vista vengono
conservati, ma la query restituisce soltanto ID lead, data creazione, Campagna e
UTM campaign. Nomi, email e telefoni non vengono richiesti.

La registrazione Entra configurata è:

```text
Tenant ID: 958e2a97-c0ab-4216-9685-ca29d4b59bd1
Client ID: 341c89da-84eb-49cd-a69d-85ce9c3979a8
Environment: https://dynamicaretail.crm4.dynamics.com
```

Prima del collegamento, in Power Platform Admin Center aggiungere questa app
come **Application User** nell'ambiente Dynamica Retail e assegnarle un ruolo
dedicato con sola lettura a livello organizzazione su Lead, viste e sulle
eventuali tabelle collegate dalla vista. Non assegnare permessi di creazione,
modifica o cancellazione.

Copiare `.env.example` nel `.env` locale e impostare soltanto sul PC aziendale:

```text
DYNAMICS_CLIENT_SECRET=<valore del secret esistente>
DYNAMICS_ENABLED=false
```

Il portale Entra mostra l'esistenza del secret ma non permette di recuperarne
nuovamente il valore: se non è stato conservato, crearne uno nuovo e copiarlo
subito nel `.env`.

Non inviare il secret in chat e non commetterlo. Se il riconoscimento automatico
dei due campi personalizzati non è univoco, il controllo restituisce i nomi delle
variabili da valorizzare: `DYNAMICS_CAMPAIGN_FIELD` e
`DYNAMICS_UTM_CAMPAIGN_FIELD`.

Con il flag ancora disattivato, confrontare API ed export sulla stessa data:

```powershell
.\.venv\Scripts\python.exe -m src.validate_dynamics --end-date 2026-07-20
```

Il comando non pubblica né modifica i latest. Attivare `DYNAMICS_ENABLED=true`
solo quando totale, allocazioni, unmatched e ambiguous coincidono esattamente.
In produzione un errore Dynamics conserva le ultime lead valide e marca il
report come `partial`/`crm:stale`.

Il file locale `data/raw/dynamics_raw.csv` contiene soltanto l'ID trasformato in
hash, Campagna, UTM, data e risultato del matching. È escluso da GitHub.

## Write-back Google Sheet

Prima di generare `data/report_data.csv`, la pipeline aggiorna nel worksheet
`manual_inputs` i quattro controlli periodo e le formule di stima con:

```powershell
.\.venv\Scripts\python.exe -m src.update_sheet_estimates
```

Le stime lead usano sempre i giorni di calendario. Lo spending usa i giorni di
calendario per le campagne normali e i soli lunedi-venerdi per le campagne con
un riferimento `DEM` in funnel, piattaforma, canale o nome campagna. Il primo
giorno del mese viene chiuso automaticamente il mese precedente.

Dopo la generazione di `data/report_data.csv`, la pipeline aggiorna lead,
speso e formule derivate nel worksheet con:

```powershell
.\.venv\Scripts\python.exe -m src.writeback_google_sheet
```

Il periodo predefinito va dal primo giorno del mese a ieri. Per verificare un
periodo senza scrivere:

```powershell
.\.venv\Scripts\python.exe -m src.writeback_google_sheet --dry-run --end-date 2026-07-17
```

Il write-back non modifica mai A:K o W, non inserisce righe e usa gli ID
campagna per il matching. Le campagne DEM, prive di ID, sono riconosciute solo
tramite nome esatto e mantengono la formula `lead x CPL`. Prima della prima
scrittura viene creata una copia nascosta di `manual_inputs`; il worksheet
`Mapping campagne-crm` viene soltanto letto.

## Metriche giornaliere dashboard

La pipeline genera `data/report_daily_metrics.csv` dopo `report_data.csv`. Il
file contiene soltanto aggregati giornalieri per campagna: speso, numero lead,
ID campagna e riga del planning. Non contiene Id Lead, UTM, date/ore individuali
o altri dati personali CRM.

La dashboard usa questo file per ricalcolare campagne, KPI, subtotali e totale
su qualsiasi intervallo selezionato. Le lead CRM `Area Clienti` non vengono
distribuite sulle cinque campagne: le righe campagna mantengono spesa e dati di
pianificazione, mentre lead effettive, CPL e delta dipendenti dalle lead sono
esposti una sola volta in `TOT Area Clienti`. Lo speso DEM resta `lead x CPL`.
Per le DEM, la stima spending distribuisce il budget mensile soltanto sui giorni
da lunedi a venerdi: sabato e domenica sono esclusi, mentre le festivita
infrasettimanali restano incluse. Le altre campagne continuano a usare tutti i
giorni di calendario.
CSV ed Excel scaricati includono le righe `TOT Area Clienti`, `TOT Lead Veloce`,
`TOT DEM` e `TOTALE GENERALE` relative alle date selezionate.

## Storico mensile dashboard

Quando il report latest copre un mese completo, la pipeline crea una sola copia
congelata in:

```text
data/history/YYYY-MM/
  report_data.csv
  report_daily_metrics.csv
  last_update.json
```

La copia non viene sovrascritta. Le vecchie cartelle dell'archivio locale
vengono recuperate soltanto se contengono un mese completo; le copie parziali
sono ignorate. Lo storico pubblicato contiene dati aggregati, mentre lo storico
giornaliero completo continua a restare soltanto sul PC.

La dashboard apre per impostazione predefinita il mese corrente dal giorno 1 a
ieri. Il filtro può selezionare un intervallo interno a un mese storico, ma non
può attraversare due mesi. KPI, grafici, tabella, alert e download CSV/Excel
vengono ricalcolati sul periodo selezionato.

Le tre coppie storica/`QUINTO DIGITALE` identificate dalle righe planning
`9/10`, `11/12` e `13/14` restano visibili come campagne separate. Per ogni
coppia, Stima Lead, Delta Lead, CPL Effettivo e Delta CPL sono metriche uniche
calcolate sulla somma della coppia; le Lead Effettive restano invece separate
per campagna. Dashboard, CSV, Excel e write-back Google Sheet applicano la
stessa regola, basata sulle righe planning e non sul colore delle celle.

## Verifica locale API

Sul solo PC aziendale impostare nel file `.env`:

```text
LOCAL_VERIFICATION_MODE=true
```

Avviare poi `streamlit run app.py`. In fondo alla dashboard comparirà la sezione
richiudibile **Verifica locale collegamenti Ads**. Il pulsante interroga entrambe
le API in sola lettura e mostra piattaforma, campaign ID, nome, periodo, speso,
stato ed errore semplice. Lasciare il flag assente o `false` su Streamlit Cloud:
la sezione non viene renderizzata nella versione cliente.

Questo progetto fa tre cose:

1. genera un `refresh_token` OAuth per Google Ads;
2. invia query alle API Google Ads e Meta Ads;
3. salva i risultati in un database SQLite locale.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## 1. Autorizza Google Ads

```powershell
.\.venv\Scripts\python.exe scripts\get_refresh_token.py
```

Si aprira il browser. Accedi con l'account Google che ha accesso a Google Ads e autorizza l'app. Lo script salvera automaticamente il refresh token nel file `.env`.

Se Google mostra `Errore 403: access_denied` e dice che l'app non ha completato la verifica, l'app OAuth e in modalita test. Vai in Google Cloud Console, apri il progetto del client OAuth, entra in `APIs & Services` > `OAuth consent screen` > `Audience` e aggiungi l'email usata per il login nella sezione `Test users`. Poi rilancia questo comando.

## 2. Verifica gli account accessibili

```powershell
.\.venv\Scripts\python.exe scripts\list_accessible_customers.py
```

Se `7971744254` e un manager account, usa questo valore come `GOOGLE_ADS_LOGIN_CUSTOMER_ID` e metti in `GOOGLE_ADS_CUSTOMER_ID` l'account cliente da interrogare.

## 3. Esporta le campagne

```powershell
.\.venv\Scripts\python.exe scripts\export_campaigns.py --during LAST_30_DAYS
```

Per interrogare un account specifico:

```powershell
.\.venv\Scripts\python.exe scripts\export_campaigns.py --customer-id 5098776326 --login-customer-id 7971744254 --during LAST_30_DAYS
```

I dati vengono salvati in `data\google_ads.db`, tabella `campaign_performance`.

Per vedere le ultime righe salvate:

```powershell
.\.venv\Scripts\python.exe scripts\preview_campaigns.py
```

Campi esportati:

- `campaign.name`
- `campaign.advertising_channel_type`
- `metrics.cost_micros`
- `metrics.clicks`
- `metrics.impressions`
- `metrics.conversions`
- `cpl`, calcolato come speso / conversioni

## Meta Ads

La configurazione Meta viene letta da `.env`:

```env
META_APP_ID=...
META_ACCESS_TOKEN=...
META_AD_ACCOUNT_ID=620126578089795
META_API_VERSION=v25.0
```

Per esportare gli insights degli ultimi 30 giorni a livello campagna:

```powershell
.\.venv\Scripts\python.exe scripts\export_meta_insights.py --date-preset last_30d
```

I dati Meta vengono salvati nello stesso database SQLite, ma in una tabella separata: `meta_campaign_performance`.

Per vedere le ultime righe Meta salvate:

```powershell
.\.venv\Scripts\python.exe scripts\preview_meta_campaigns.py
```

Campi esportati:

- `campaign_name`
- `channel`, fisso a `META`
- `spend`
- `clicks`
- `impressions`
- `leads`, calcolato dalle azioni Meta legate ai lead
- `cpl`, calcolato come speso / lead
- `actions_json`, per conservare il dettaglio conversioni grezzo restituito da Meta
