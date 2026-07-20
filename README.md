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

## Write-back Google Sheet

Dopo la generazione di `data/report_data.csv`, la pipeline aggiorna il
worksheet `manual_inputs` con:

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
su qualsiasi intervallo selezionato. Area Clienti viene ripartita sulle cinque
righe dopo aver sommato l'intero intervallo; lo speso DEM resta `lead x CPL`.
CSV ed Excel scaricati includono le righe `TOT Area Clienti`, `TOT Lead Veloce`,
`TOT DEM` e `TOTALE GENERALE` relative alle date selezionate.

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
