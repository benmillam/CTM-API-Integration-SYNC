# CTM API Integration - ETL Pipeline

## Overview

This repository contains an ETL pipeline that synchronizes CallTrackingMetrics (CTM) data with Google BigQuery using Google Cloud Run Jobs and scheduled queries. The system automatically extracts call activities and account data from the CTM API and loads it into BigQuery for analytics and reporting.

## Architecture

```
CTM API → Cloud Run Jobs → BigQuery → Scheduled Queries → Final Tables
```

### Data Flow
1. **CTM API Extraction**: Python jobs fetch data from CallTrackingMetrics API
2. **BigQuery Loading**: Raw data is loaded into staging tables
3. **Data Processing**: Scheduled queries combine and process the data
4. **Final Tables**: Clean, processed data available for analysis

## Project Structure

```
├── main.py              # Main ETL script
├── requirements.txt     # Python dependencies
├── Dockerfile          # Container configuration
├── deploy.sh           # Deployment script
├── .env               # Environment variables (not in repo)
└── docs/              # Documentation
```

## BigQuery Datasets

### `ctm_data` (Production Dataset)
- **`accounts`**: Account information from CTM API
- **`activities_raw_daily`**: Daily call activities from CTM API
- **`activities_raw_final_batch`**: Final batch of activities data
- **`activities_combined`**: View combining daily and batch data
- **`activities_combined_deduped` / `activities_combined_deduped_90d`**: Truth-preferring dedup views for daily, lookback, and batch activity candidates
- **`activities_data`**: Final processed table (scheduled query output)

### `ctm_data_batch` (Batch Processing Dataset)
- **`activities_raw`**: Raw activities from batch processing
- **`activities_raw_batch_1-6`**: Individual batch tables
- **`activities_batch_column_diff`**: Column difference analysis

## Cloud Run Jobs

The system uses three Cloud Run jobs in the `us-central1` region:

### 1. CTM Accounts Sync Job (`ctm-accounts-sync-job`)
- **Purpose**: Syncs account data from CTM API
- **Schedule**: Daily at 12:00 AM UTC
- **Status**: Active and running successfully
- **Target Table**: `ctm_data.accounts`

### 2. CTM Daily Job (`ctm-daily-job`)
- **Purpose**: Syncs daily activities data from CTM API
- **Schedule**: Daily at 12:00 AM UTC
- **Status**: Active and running successfully
- **Target Table**: `ctm_data.activities_raw_daily`
- **Lead fields**: Extracts `valid_lead`, `lead_summary`, and `is_spam` from CTM call custom fields, including nested contact or score field locations

### 3. CTM Batch Job (`ctm-batch-job`)
- **Purpose**: One-time batch processing of historical data
- **Status**: Completed (DO NOT RE-RUN)
- **Target**: `ctm_data_batch` dataset
- **⚠️ WARNING**: This job has already been executed and created all necessary batch tables. Re-running will create duplicate data.

## Monitoring and Management

### Cloud Run Jobs Status
- View job status in Google Cloud Console → Cloud Run → Jobs
- Check execution history and logs for each job
- Monitor success/failure rates and execution times

### Logs and Debugging
- **Location**: Cloud Run → Job Details → Logs tab
- **Log Levels**: INFO, WARNING, ERROR
- **Key Metrics**: Records processed, API calls made, errors encountered

### Cloud Scheduler
- **Location**: Google Cloud Console → Cloud Scheduler
- **Jobs**: 
  - `ctm-accounts-sync-daily-schedule`
  - `ctm-daily-job-scheduler-trigger`
- **Capabilities**: View, edit, pause, or manually trigger schedules

## Scheduled Queries

### Activities Data Processing
- **Query Name**: "Activities sync"
- **Schedule**: Every 1 hour
- **Purpose**: Combines and dedups data from `activities_raw_daily`, `activities_raw_daily_lookback`, and `activities_raw_final_batch`
- **Output**: `ctm_data.activities_data`
- **SQL**: DELETE+INSERT 90-day refresh from `ctm_data.activities_combined_deduped_90d` after the manual transfer-config repoint

### Query Management
- **Location**: BigQuery → Scheduled Queries
- **Monitoring**: View execution history and success rates
- **Configuration**: Hourly refresh ensures data freshness

## Quick Status Check

### Verify System Health
1. **Check Job Status**: Cloud Run → Jobs → Verify "Succeeded" status
2. **Review Logs**: Click job → Logs tab → Look for "JOB_SUCCESS" messages
3. **Data Validation**: Query latest records in BigQuery tables
4. **Schedule Status**: Cloud Scheduler → Confirm jobs are "Enabled"

### Key Monitoring Points
- Jobs should show "Succeeded" status after execution
- Logs should contain structured success messages
- BigQuery tables should have recent data (check timestamps)
- Scheduled queries should run every hour without errors

## Data Usage

### Primary Tables for Analysis
- **`ctm_data.activities_data`**: Main table for call activities analysis
- **`ctm_data.accounts`**: Account information and metadata
- **`ctm_data.activities_combined`**: Real-time view of combined activities
- **`ctm_data.activities_combined_deduped`**: Real-time view of combined activities with truth-preferring duplicate resolution

### Query Examples
```sql
-- Latest call activities
SELECT * FROM `ctm_data.activities_data` 
ORDER BY created_at DESC 
LIMIT 100;

-- Account summary
SELECT account_name, status, created_at 
FROM `ctm_data.accounts`;
```

## Important Notes

### Batch Job Warning
**🚨 CRITICAL**: The `ctm-batch-job` has already processed historical data into the `ctm_data_batch` dataset. This job should NOT be re-executed as it will create duplicate tables and consume unnecessary resources.

### Data Freshness
- **Accounts**: Updated daily at 12:00 AM UTC
- **Activities**: Updated daily at 12:00 AM UTC, processed hourly
- **Combined View**: Real-time combination of daily and batch data

### Credentials
- CTM API credentials are provided to Cloud Run Jobs from Secret Manager secrets `CTM_ACCESS_KEY` and `CTM_SECRET_KEY`.
- Do not store `.env` files in source archives or container images.

### Resource Management
- Jobs are configured with appropriate memory (2Gi) and CPU (1) limits
- Automatic retries (max 3) handle temporary failures
- 1-hour timeout prevents runaway processes

## Support and Maintenance

### Regular Maintenance
- Monitor job execution logs weekly
- Review BigQuery storage usage monthly
- Update API credentials as needed
- Monitor CTM API rate limits and usage

### Troubleshooting
- Check job logs for error messages
- Verify API credentials in environment variables
- Ensure BigQuery permissions are configured correctly
- Monitor Cloud Scheduler job status

For detailed deployment and configuration instructions, see the additional documentation files in this repository.
