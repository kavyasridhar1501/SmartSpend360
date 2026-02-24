# SmartSpend360

Production-grade financial analytics platform built on a fully free/open-source cloud stack. Zero-cost deployment using AWS Free Tier + Databricks Community Edition.

## Architecture

```
[Plaid / Alpha Vantage / Open Exchange APIs]
        │
        ▼
┌─────────────────────┐
│  Apache Airflow      │  ← DAGs: ingest every 15min / 6am / 8am UTC
│  (Docker / EC2)      │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────────────────────────┐
│           AWS S3 Data Lakehouse          │
│  /bronze/  →  /silver/  →  /gold/        │
│  (raw JSON)   (Parquet)   (Delta/Parquet)│
└─────────┬───────────────────────────────┘
          │
          ├──────────────────────────────────────────────────────┐
          ▼                                                       ▼
┌──────────────────┐                                   ┌──────────────────┐
│ Databricks CE    │                                   │ dbt Core         │
│ (PySpark + ML)   │  Isolation Forest + Prophet       │ (Semantic Layer) │
│ 5 notebooks      │  → anomaly scores, forecasts      │ Athena queries   │
└────────┬─────────┘                                   └────────┬─────────┘
         │                                                       │
         └──────────────────────┬────────────────────────────────┘
                                ▼
                    ┌──────────────────────┐
                    │   AWS Athena         │
                    │ (Serverless SQL)     │
                    └──────────┬───────────┘
                               │
                               ▼
              ┌────────────────────────────────┐
              │  FastAPI Backend               │
              │  (Railway.app free tier)        │
              │  9 endpoints + API key auth     │
              └───────────────┬────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
    ┌──────────────┐  ┌──────────────┐ ┌──────────────┐
    │ React SPA    │  │ AWS DynamoDB │ │ Airflow REST │
    │ (Vercel)     │  │ (alerts,     │ │ API trigger  │
    │ 6 pages      │  │  metrics,    │ │              │
    │ Recharts     │  │  forecasts)  │ │              │
    └──────────────┘  └──────────────┘ └──────────────┘
```

## Features

- **Real-time ingestion** — Plaid transactions, Alpha Vantage ETF prices, Open Exchange FX rates
- **Lakehouse architecture** — Bronze → Silver → Gold on S3 with Delta format
- **ML anomaly detection** — Isolation Forest (contamination=0.05, 100 estimators)
- **Cash flow forecasting** — Facebook Prophet with weekly seasonality + US holidays
- **Semantic layer** — dbt Core models on Athena (staging → intermediate → marts)
- **9 REST endpoints** — paginated, authenticated FastAPI with Pydantic validation
- **React dashboard** — 6 pages with Recharts, real-time pipeline status, what-if simulator
- **Mock data generator** — makes app fully functional with zero real API keys
- **CI/CD** — GitHub Actions → Railway (backend) + Vercel (frontend)

## Prerequisites

- Python 3.11+
- Node.js 20+
- AWS account (free tier) — [Sign up](https://aws.amazon.com/free/)
- Databricks Community Edition — [Sign up](https://community.cloud.databricks.com/)
- Docker (for Airflow)

## Quick Start (5 commands)

```bash
# 1. Clone and configure environment
cp .env.template .env
# Edit .env with your AWS credentials and API keys

# 2. Provision AWS infrastructure
pip install boto3
python scripts/setup_aws.py

# 3. Generate mock data (makes dashboard work immediately)
pip install boto3 pyarrow pandas
python data/seed/generate_mock_data.py

# 4. Start the backend
cd backend && pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 5. Start the frontend (new terminal)
cd frontend && npm install && npm run dev
# → Open http://localhost:3000
```

## Local Airflow (Docker)

```bash
cd airflow
docker-compose -f docker-compose.airflow.yml up -d
# → Airflow UI at http://localhost:8080 (admin/admin)
```

## Backend API

Base URL: `http://localhost:8000` (local) or your Railway URL

All endpoints require `X-API-Key` header except `GET /health` and `GET /api/v1/pipeline/status`.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/api/v1/transactions` | Paginated transaction list |
| GET | `/api/v1/anomalies` | Anomaly list with ML scores |
| POST | `/api/v1/anomalies/{id}/acknowledge` | Acknowledge anomaly |
| GET | `/api/v1/forecast` | Prophet forecast + runway |
| GET | `/api/v1/metrics/summary` | KPI summary |
| GET | `/api/v1/pipeline/status` | Pipeline stage status |
| POST | `/api/v1/pipeline/trigger` | Trigger Airflow DAG |
| POST | `/api/v1/alerts` | Create alert rule |
| GET | `/api/v1/alerts/{user_id}` | List alerts + events |

**API Docs**: `http://localhost:8000/docs` (Swagger UI)

## Running Tests

```bash
cd backend
pytest tests/ --cov=app --cov-report=term-missing -v
```

## Databricks Setup

1. Sign up at [community.cloud.databricks.com](https://community.cloud.databricks.com/)
2. Create a cluster (Databricks Runtime 14.x, Python 3.11)
3. Install libraries on cluster: `prophet`, `scikit-learn`, `boto3`, `pyarrow`
4. Import notebooks from `databricks/` folder via Workspace → Import
5. Set cluster ID in `.env` as `DATABRICKS_CLUSTER_ID`
6. Set notebook base path as `DATABRICKS_NOTEBOOK_BASE`

## dbt Setup

```bash
pip install dbt-athena-community
cd dbt
# Configure profiles.yml with your Athena credentials
dbt debug       # Test connection
dbt run         # Run all models
dbt test        # Run data tests
dbt docs generate && dbt docs serve  # View lineage graph
```

## Deployment

### Backend → Railway

```bash
# Install Railway CLI
npm install -g @railway/cli
railway login

cd backend
railway init
railway up

# Set environment variables in Railway dashboard
# → Settings → Variables → add all from .env.template
```

### Frontend → Vercel

```bash
npm install -g vercel
cd frontend
vercel

# Set environment variables:
# VITE_API_URL = your Railway backend URL
# VITE_API_KEY = your API key
```

### EC2 Airflow (Optional)

```bash
# Launch t2.micro (Ubuntu 22.04 AMI)
# SSH into instance, then:
sudo apt update && sudo apt install docker.io docker-compose-plugin -y
git clone https://github.com/your-org/smartspend360.git
cd smartspend360/airflow
cp ../.env ./
docker compose -f docker-compose.airflow.yml up -d
```

## Environment Variables Reference

See `.env.template` for all required variables.

Key variables:
- `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` — AWS IAM credentials
- `PLAID_CLIENT_ID` / `PLAID_SECRET` — Plaid API (sandbox is free)
- `ALPHA_VANTAGE_KEY` — Alpha Vantage (25 calls/day free)
- `OPEN_EXCHANGE_APP_ID` — Open Exchange Rates (1000 calls/month free)
- `DATABRICKS_HOST` / `DATABRICKS_TOKEN` — Databricks Community Edition
- `API_KEY` — FastAPI authentication key

## Cost Analysis (All Free Tier)

| Service | Free Tier | Usage |
|---------|-----------|-------|
| AWS S3 | 5 GB storage | ~50 MB/month of Parquet |
| AWS DynamoDB | 25 GB, 200M req | ~1000 items |
| AWS Athena | $5/TB scanned | ~10 MB queries |
| Databricks CE | Free forever | 1 notebook cluster |
| Railway.app | $5 credit/month | Backend ~$1-2 |
| Vercel | Hobby free | Frontend hosting |
| Plaid | Sandbox: free | 500 test transactions |
| Alpha Vantage | 25 calls/day | 3 symbols/day |

**Total estimated cost: $0-2/month**

## Project Structure

```
smartspend360/
├── airflow/dags/           # 4 Airflow DAGs
├── databricks/             # 5 PySpark notebooks
├── dbt/models/             # staging → intermediate → marts SQL
├── backend/
│   ├── app/api/v1/routes/  # 6 route modules
│   ├── app/services/       # DynamoDB + Athena clients
│   ├── app/models/         # Pydantic schemas
│   └── tests/              # pytest + moto (90%+ coverage)
├── frontend/src/
│   ├── pages/              # 6 React pages
│   ├── hooks/              # React Query hooks
│   ├── components/         # UI + chart components
│   └── lib/                # API client + utilities
├── data/seed/              # Mock data generator
├── scripts/                # AWS setup + teardown
└── .github/workflows/      # CI/CD pipelines
```

## Screenshots

> After running `generate_mock_data.py`, navigate to `http://localhost:3000`:

- **Dashboard** — KPI cards, 90-day spend area chart, category donut, anomaly widget
- **Transactions** — Filterable table with anomaly scores, CSV export, slide-over detail
- **Anomalies** — Timeline view grouped by date with acknowledge workflow
- **Forecast** — Prophet chart with confidence bands, what-if simulator
- **Alerts** — Alert rule configuration and history
- **Pipeline** — 7-stage architecture diagram with live status

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Run tests: `cd backend && pytest tests/ -v`
4. Submit a pull request

## License

MIT License — see [LICENSE](LICENSE) for details.
