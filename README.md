# Ads local export

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
