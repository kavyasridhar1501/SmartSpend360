# SmartSpend360 — End-to-End Deployment Guide

This guide walks you through deploying SmartSpend360 from zero, assuming no prior knowledge. Read every section in order before skipping ahead.

---

## Table of Contents

1. [What You Are Deploying](#1-what-you-are-deploying)
2. [Accounts You Need to Create](#2-accounts-you-need-to-create)
3. [Tools to Install on Your Computer](#3-tools-to-install-on-your-computer)
4. [Step 1 — AWS Setup](#4-step-1--aws-setup)
5. [Step 2 — Get Third-Party API Keys](#5-step-2--get-third-party-api-keys)
6. [Step 3 — Clone the Project](#6-step-3--clone-the-project)
7. [Step 4 — Configure Environment Variables](#7-step-4--configure-environment-variables)
8. [Step 5 — Deploy the Backend (Railway)](#8-step-5--deploy-the-backend-railway)
9. [Step 6 — Deploy the Frontend (Vercel)](#9-step-6--deploy-the-frontend-vercel)
10. [Step 7 — Connect Frontend to Backend](#10-step-7--connect-frontend-to-backend)
11. [Step 8 — Run Airflow Locally (Optional)](#11-step-8--run-airflow-locally-optional)
12. [Step 9 — Verify Everything Works](#12-step-9--verify-everything-works)
13. [Troubleshooting](#13-troubleshooting)

---

## 1. What You Are Deploying

SmartSpend360 is a financial analytics platform made of three independently deployed pieces:

| Piece | Technology | Where It Runs |
|-------|-----------|---------------|
| **Frontend** (the website users see) | React + TypeScript | Vercel (free) |
| **Backend API** (business logic, data) | Python + FastAPI | Railway (free tier) |
| **Data Storage** | AWS DynamoDB + S3 + Athena | AWS cloud |
| **Data Pipeline** (optional) | Apache Airflow | Your machine (Docker) |

The frontend talks to the backend. The backend talks to AWS. You control all three with environment variables (`.env` files).

---

## 2. Accounts You Need to Create

Create these accounts before starting. All have free tiers.

| Service | URL | Why You Need It | Cost |
|---------|-----|----------------|------|
| **AWS** | https://aws.amazon.com | Stores data (DynamoDB, S3, Athena) | Free tier covers this project |
| **Railway** | https://railway.app | Hosts the Python backend | Free $5/month credit |
| **Vercel** | https://vercel.com | Hosts the React frontend | Free forever for hobby projects |
| **GitHub** | https://github.com | Source code host (needed for Vercel/Railway deploys) | Free |
| **Plaid** | https://dashboard.plaid.com/signup | Financial data API | Free sandbox |
| **Alpha Vantage** | https://www.alphavantage.co/support/#api-key | Stock/market data API | Free (25 calls/day) |
| **Open Exchange Rates** | https://openexchangerates.org/signup/free | Currency exchange rates | Free (1000 calls/month) |

---

## 3. Tools to Install on Your Computer

### 3.1 Git

Git is used to download the project and send code changes to GitHub.

- **Check if installed:** Open a terminal and run `git --version`
- **Install:** Download from https://git-scm.com/downloads and follow the installer

### 3.2 Node.js (v20 or later)

Node.js is needed to run and build the frontend locally.

- **Check if installed:** `node --version` (must show v20.x.x or higher)
- **Install:** Download the LTS version from https://nodejs.org

### 3.3 Python (v3.11)

Python runs the backend locally for testing.

- **Check if installed:** `python3 --version`
- **Install:** Download from https://www.python.org/downloads/ — choose Python 3.11.x

### 3.4 AWS CLI

The AWS CLI lets you configure your AWS credentials from the terminal.

- **Install:** Follow https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html
- **Check if installed:** `aws --version`

### 3.5 Docker (for Airflow — optional)

Only needed if you want to run the data pipeline locally.

- **Install:** Download Docker Desktop from https://www.docker.com/products/docker-desktop/

---

## 4. Step 1 — AWS Setup

The backend uses three AWS services: S3 (file storage), DynamoDB (database), and Athena (analytics queries). You need to set these up before deploying the backend.

### 4.1 Create an AWS Account

1. Go to https://aws.amazon.com and click **Create an AWS Account**
2. Enter your email, choose a root account password
3. Add a payment method (you will NOT be charged unless you exceed free tier)
4. Complete phone verification
5. Choose the **Basic (Free)** support plan

### 4.2 Create an IAM User (Never use root credentials in code)

1. Log in to the AWS Console at https://console.aws.amazon.com
2. In the search bar at the top, type **IAM** and click it
3. In the left sidebar, click **Users**, then click **Create user**
4. Enter username: `smartspend360-app`
5. Click **Next**
6. Choose **Attach policies directly**
7. Search for and check these policies:
   - `AmazonDynamoDBFullAccess`
   - `AmazonS3FullAccess`
   - `AmazonAthenaFullAccess`
8. Click **Next**, then **Create user**
9. Click on the newly created user `smartspend360-app`
10. Click the **Security credentials** tab
11. Scroll down to **Access keys**, click **Create access key**
12. Choose **Application running outside AWS**, click **Next**
13. Click **Create access key**
14. **IMPORTANT:** Copy both values now — you cannot see the secret key again:
    - **Access key ID** (looks like: `AKIAIOSFODNN7EXAMPLE`)
    - **Secret access key** (looks like: `wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY`)

### 4.3 Create S3 Buckets

S3 buckets store raw and processed data files.

1. In the AWS Console search bar, type **S3** and click it
2. Click **Create bucket**
3. **Bucket name:** `smartspend360-datalake`
4. **AWS Region:** `us-east-1` (US East N. Virginia — keep this consistent everywhere)
5. Leave all other settings as default
6. Click **Create bucket**
7. Repeat steps 2-6 for a second bucket named: `smartspend360-athena-results`

You should now have two buckets:
- `smartspend360-datalake`
- `smartspend360-athena-results`

### 4.4 Create DynamoDB Tables

DynamoDB is the main database for alerts, metrics, forecasts, and pipeline runs.

1. In the AWS Console search bar, type **DynamoDB** and click it
2. Click **Create table**

Create the following 4 tables one by one (same settings for each):

**Table 1:**
- Table name: `ss360-alerts`
- Partition key: `alert_id` (type: String)
- Click **Create table**

**Table 2:**
- Table name: `ss360-metrics`
- Partition key: `metric_id` (type: String)
- Click **Create table**

**Table 3:**
- Table name: `ss360-forecasts`
- Partition key: `forecast_id` (type: String)
- Click **Create table**

**Table 4:**
- Table name: `ss360-pipeline-runs`
- Partition key: `run_id` (type: String)
- Click **Create table**

Wait for all four tables to show status **Active** before continuing.

### 4.5 Set Up Athena

Athena lets you run SQL queries against files stored in S3.

1. In the AWS Console search bar, type **Athena** and click it
2. If prompted with a "Get started" page, click **Explore the query editor**
3. Click **Settings** tab (top right area)
4. Under **Query result location**, click **Manage**
5. Enter: `s3://smartspend360-athena-results/query-results/`
6. Click **Save**
7. Click the **Editor** tab
8. In the query box, run this SQL to create the database:

```sql
CREATE DATABASE IF NOT EXISTS smartspend360_db;
```

9. Click **Run**

10. Create the Athena workgroup:
    - Click **Workgroups** in the left sidebar
    - Click **Create workgroup**
    - Name: `smartspend360`
    - Under **Query result configuration**, set location to: `s3://smartspend360-athena-results/query-results/`
    - Click **Create workgroup**

### 4.6 Configure AWS CLI Locally

Run this in your terminal to store your AWS credentials locally:

```bash
aws configure
```

Enter when prompted:
- **AWS Access Key ID:** (paste the key you copied in step 4.2)
- **AWS Secret Access Key:** (paste the secret you copied in step 4.2)
- **Default region name:** `us-east-1`
- **Default output format:** `json`

Verify it works:

```bash
aws s3 ls
```

You should see your two buckets listed.

---

## 5. Step 2 — Get Third-Party API Keys

### 5.1 Plaid API (Financial Data)

1. Go to https://dashboard.plaid.com/signup and create an account
2. After logging in, go to **Team Settings → Keys**
3. Copy your **Client ID** and **Sandbox Secret**
4. Your `PLAID_ENV` will be `sandbox` (free, uses test data)
5. To get a `PLAID_ACCESS_TOKEN`, use Plaid's quickstart or sandbox tool — for now you can use the placeholder value and the backend will use mock data

### 5.2 Alpha Vantage (Market Data)

1. Go to https://www.alphavantage.co/support/#api-key
2. Fill in your name and email, click **GET FREE API KEY**
3. Copy the API key shown on the next page

### 5.3 Open Exchange Rates (Currency Data)

1. Go to https://openexchangerates.org/signup/free
2. Fill in the form and verify your email
3. After logging in, go to your **Dashboard**
4. Copy your **App ID**

---

## 6. Step 3 — Clone the Project

Open a terminal (on Windows use **Git Bash** or **PowerShell**).

```bash
# Navigate to where you want the project (e.g., your Desktop)
cd ~/Desktop

# Clone the repository (replace with your actual GitHub URL)
git clone https://github.com/kavyasridhar1501/SmartSpend360.git

# Move into the project folder
cd SmartSpend360
```

---

## 7. Step 4 — Configure Environment Variables

Environment variables are secret settings your app reads at runtime. They are **never committed to git**.

### 7.1 Backend `.env`

```bash
# Copy the template
cp .env.template backend/.env
```

Open `backend/.env` in any text editor and fill in every value:

```bash
# AWS Credentials (from step 4.2)
AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE
AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
AWS_REGION=us-east-1

# S3 (bucket names you created in step 4.3)
S3_BUCKET_NAME=smartspend360-datalake
S3_RESULTS_BUCKET=smartspend360-athena-results

# DynamoDB (table names from step 4.4)
DYNAMODB_ALERTS_TABLE=ss360-alerts
DYNAMODB_METRICS_TABLE=ss360-metrics
DYNAMODB_FORECASTS_TABLE=ss360-forecasts
DYNAMODB_PIPELINE_TABLE=ss360-pipeline-runs

# Plaid (from step 5.1)
PLAID_CLIENT_ID=your_plaid_client_id
PLAID_SECRET=your_plaid_sandbox_secret
PLAID_ENV=sandbox
PLAID_ACCESS_TOKEN=access-sandbox-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx

# Alpha Vantage (from step 5.2)
ALPHA_VANTAGE_KEY=your_alpha_vantage_key

# Open Exchange Rates (from step 5.3)
OPEN_EXCHANGE_APP_ID=your_open_exchange_app_id

# FastAPI — generate a random secure key for API_KEY
# Run this command to generate one: python3 -c "import secrets; print(secrets.token_hex(32))"
API_KEY=paste_your_generated_key_here
API_KEY_NAME=X-API-Key
APP_ENV=production
APP_VERSION=1.0.0
LOG_LEVEL=INFO

# Athena (from step 4.5)
ATHENA_WORKGROUP=smartspend360
ATHENA_DATABASE=smartspend360_db
ATHENA_OUTPUT_LOCATION=s3://smartspend360-athena-results/query-results/

# CORS — update after you deploy the frontend (step 9)
CORS_ORIGINS=http://localhost:3000

# Railway sets PORT automatically — leave as is
PORT=8000
```

**Generate a secure API key** by running:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Copy the output and use it as your `API_KEY`. Save this value — you will need it for the frontend too.

### 7.2 Frontend `.env`

```bash
# Copy the template
cp frontend/.env.example frontend/.env
```

Open `frontend/.env` and fill in:

```bash
VITE_API_URL=http://localhost:8000
VITE_API_KEY=paste_the_same_API_KEY_you_generated_above
```

---

## 8. Step 5 — Deploy the Backend (Railway)

Railway is a cloud platform that runs your Python backend 24/7.

### 8.1 Push Code to GitHub

If you forked the repo, skip to 8.2. Otherwise:

1. Create a new repository on GitHub at https://github.com/new
2. Name it `SmartSpend360`, leave it **Private**, click **Create repository**
3. In your terminal:

```bash
cd ~/Desktop/SmartSpend360
git remote set-url origin https://github.com/YOUR_GITHUB_USERNAME/SmartSpend360.git
git push -u origin main
```

### 8.2 Create a Railway Account and Project

1. Go to https://railway.app and click **Login** → **Login with GitHub**
2. Authorize Railway to access your GitHub
3. Click **New Project**
4. Click **Deploy from GitHub repo**
5. Find and select your `SmartSpend360` repository
6. Railway will detect the `backend/` folder. If prompted, set the **Root Directory** to `backend`
7. Railway will auto-detect the `Dockerfile` inside `backend/`

### 8.3 Add Environment Variables to Railway

1. In your Railway project, click on the service that was created
2. Click the **Variables** tab
3. Click **+ New Variable** and add each variable from your `backend/.env` file one by one

   You can also use **RAW Editor** — click it, then paste all your variables in `KEY=VALUE` format (one per line).

   > Do NOT include the `PORT` variable — Railway sets that automatically.

4. After adding all variables, Railway will automatically redeploy

### 8.4 Get Your Backend URL

1. Click the **Settings** tab in your Railway service
2. Under **Networking**, click **Generate Domain**
3. Your backend URL will look like: `https://smartspend360-production.up.railway.app`
4. Copy this URL — you need it for the frontend

### 8.5 Verify Backend is Running

Open your browser and go to:

```
https://your-railway-url.up.railway.app/health
```

You should see a JSON response like:

```json
{"status": "healthy", "version": "1.0.0"}
```

If you see this, the backend is deployed correctly.

---

## 9. Step 6 — Deploy the Frontend (Vercel)

Vercel hosts your React frontend and serves it as a fast global website.

### 9.1 Create a Vercel Account

1. Go to https://vercel.com and click **Sign Up**
2. Choose **Continue with GitHub**
3. Authorize Vercel

### 9.2 Import Your Project

1. In the Vercel dashboard, click **Add New → Project**
2. Find your `SmartSpend360` repository and click **Import**
3. Vercel will detect it as a Vite project

### 9.3 Configure the Build Settings

In the configuration screen:

- **Framework Preset:** Vite (auto-detected)
- **Root Directory:** `frontend`
- **Build Command:** `npm run build` (auto-filled)
- **Output Directory:** `dist` (auto-filled)

### 9.4 Add Environment Variables in Vercel

Before clicking **Deploy**, scroll down to **Environment Variables** and add:

| Name | Value |
|------|-------|
| `VITE_API_URL` | Your Railway backend URL (e.g., `https://smartspend360-production.up.railway.app`) |
| `VITE_API_KEY` | The same `API_KEY` value you generated earlier |

### 9.5 Deploy

Click **Deploy**. Vercel will:
1. Clone your repo
2. Run `npm install` and `npm run build`
3. Deploy the built files to their CDN

After 1-2 minutes, you will see a green **Congratulations** screen with your URL, like:
`https://smartspend360.vercel.app`

---

## 10. Step 7 — Connect Frontend to Backend (CORS Update)

After you have both URLs, you need to tell the backend to accept requests from the frontend.

### 10.1 Update CORS in Railway

1. Go back to your Railway project → **Variables**
2. Find the `CORS_ORIGINS` variable and update it:

```
CORS_ORIGINS=https://smartspend360.vercel.app,http://localhost:3000
```

Replace `https://smartspend360.vercel.app` with your actual Vercel URL.

3. Railway will auto-redeploy with the new setting.

### 10.2 Test the Connection

1. Open your Vercel URL in a browser
2. You should see the SmartSpend360 dashboard
3. If data loads without errors, everything is connected

---

## 11. Step 8 — Run Airflow Locally (Optional)

Apache Airflow runs the data ingestion pipeline. This is optional for an initial deploy — the dashboard will show mock/seeded data without it.

### Prerequisites

- Docker Desktop installed and running

### Start Airflow

```bash
cd ~/Desktop/SmartSpend360/airflow

# Copy environment variables to airflow directory
cp ../.env.template .env
# Fill in the same values as your backend/.env

# Generate a Fernet key for Airflow encryption
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Paste the output into .env as AIRFLOW__CORE__FERNET_KEY

# Start all Airflow services
docker compose -f docker-compose.airflow.yml up -d
```

Wait about 2 minutes, then open http://localhost:8080 in your browser.

- **Username:** `admin`
- **Password:** `admin`

You will see the Airflow dashboard with your data pipeline DAGs listed.

### Run a Pipeline

1. Find the DAG named `smartspend360_pipeline` (or similar)
2. Toggle it **On** using the switch on the left
3. Click the **Play** button to trigger a manual run
4. Click into the DAG to watch tasks turn green as they succeed

---

## 12. Step 9 — Verify Everything Works

Run through this checklist after deployment:

### Backend Health Check

```bash
curl https://your-railway-url.up.railway.app/health
```

Expected response:
```json
{"status": "healthy", "version": "1.0.0"}
```

### Backend API Check (with Auth)

```bash
curl -H "X-API-Key: your_api_key_here" \
  https://your-railway-url.up.railway.app/api/v1/metrics
```

Expected: JSON data (not a 401 or 403 error)

### Frontend Check

1. Open your Vercel URL in a browser
2. The dashboard should load without a blank screen
3. Navigate to `/transactions`, `/anomalies`, `/forecast`, `/alerts`
4. No browser console errors about CORS or 401 Unauthorized

### API Documentation

Visit: `https://your-railway-url.up.railway.app/docs`

This opens the interactive Swagger UI where you can test all API endpoints manually.

---

## 13. Troubleshooting

### "CORS error" in the browser console

- Your `CORS_ORIGINS` environment variable in Railway does not include your Vercel URL
- Fix: Update `CORS_ORIGINS` in Railway variables and redeploy

### Backend shows "Internal Server Error" or crashes

- Check Railway **Logs** tab for the error message
- Most likely cause: a missing or wrong environment variable
- Fix: Review all variables in Railway match your `backend/.env` exactly

### Frontend shows a blank white page

- Check the browser's developer tools (F12) → Console tab for errors
- Most likely cause: `VITE_API_URL` is wrong or backend is not running
- Fix: Verify the Railway backend URL is correct in Vercel environment variables, then redeploy Vercel

### "401 Unauthorized" from the API

- The `VITE_API_KEY` in Vercel does not match `API_KEY` in Railway
- Fix: Make sure both use the exact same key value

### AWS errors ("NoCredentialsError" or "ResourceNotFoundException")

- AWS credentials in Railway are wrong or the DynamoDB tables/S3 buckets don't exist
- Fix: Double-check `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and `AWS_REGION` in Railway
- Verify all four DynamoDB tables exist in the `us-east-1` region

### Vercel build fails

- Check the build log in Vercel dashboard
- Most common cause: TypeScript errors in the code
- Fix: Run `npm run build` locally in the `frontend/` directory first to see the errors

### Railway deploy fails

- Check the deployment log in Railway dashboard
- Most common cause: Python package install error
- Fix: Make sure `backend/requirements.txt` has not been modified

---

## Quick Reference — All URLs and Credentials Checklist

Before going live, make sure you have all of these:

```
[ ] AWS_ACCESS_KEY_ID
[ ] AWS_SECRET_ACCESS_KEY
[ ] S3 bucket: smartspend360-datalake
[ ] S3 bucket: smartspend360-athena-results
[ ] DynamoDB table: ss360-alerts
[ ] DynamoDB table: ss360-metrics
[ ] DynamoDB table: ss360-forecasts
[ ] DynamoDB table: ss360-pipeline-runs
[ ] Athena database: smartspend360_db
[ ] Athena workgroup: smartspend360
[ ] PLAID_CLIENT_ID + PLAID_SECRET
[ ] ALPHA_VANTAGE_KEY
[ ] OPEN_EXCHANGE_APP_ID
[ ] API_KEY (your generated random key)
[ ] Railway backend URL
[ ] Vercel frontend URL
[ ] CORS_ORIGINS updated in Railway with Vercel URL
```

---

*Generated for SmartSpend360 — February 2026*
