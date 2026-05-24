# Schedules Guide

## Cloud Scheduler Overview

Cloud Scheduler automatically triggers our ETL jobs at specified times. Based on the images, we have two active schedules running daily.

## Current Schedules

### 1. Accounts Sync Schedule
- **Job Name**: `ctm-accounts-sync-daily-schedule`
- **Time**: Daily at 12:00 AM UTC
- **Target**: `ctm-accounts-sync-job`
- **Status**: Enabled
- **Purpose**: Syncs account data from CTM API to BigQuery

### 2. Daily Activities Schedule  
- **Job Name**: `ctm-daily-job-scheduler-trigger`
- **Time**: Daily at 12:00 AM UTC
- **Target**: `ctm-daily-job`
- **Status**: Enabled
- **Purpose**: Syncs daily call activities from CTM API

## Viewing Schedules

### In Google Cloud Console
1. Go to **Cloud Console → Cloud Scheduler**
2. You'll see the list of scheduled jobs
3. Check **Status** column (should be "Enabled")
4. View **Next run** and **Last run** times

### Using Command Line
```bash
# List all schedules
gcloud scheduler jobs list --location=us-central1

# View specific schedule details
gcloud scheduler jobs describe ctm-accounts-sync-daily-schedule --location=us-central1
```

## Schedule Management

### Manual Trigger
```bash
# Trigger accounts sync now
gcloud scheduler jobs run ctm-accounts-sync-daily-schedule --location=us-central1

# Trigger daily job now
gcloud scheduler jobs run ctm-daily-job-scheduler-trigger --location=us-central1
```

### Pause/Resume Schedules
```bash
# Pause schedule
gcloud scheduler jobs pause ctm-accounts-sync-daily-schedule --location=us-central1

# Resume schedule
gcloud scheduler jobs resume ctm-accounts-sync-daily-schedule --location=us-central1
```

### Update Schedule Time
```bash
# Change to run at 2 AM instead of 12 AM
gcloud scheduler jobs update http ctm-accounts-sync-daily-schedule \
    --schedule="0 2 * * *" \
    --location=us-central1
```

## Scheduled Queries (BigQuery)

### Activities Processing Query
- **Query Name**: "Activities sync"
- **Schedule**: Every 1 hour starting now
- **Purpose**: Combines data from daily and batch tables
- **Source**: `ctm_data.activities_combined` (view)
- **Destination**: `ctm_data.activities_data` (table)

### How It Works
1. Hourly query runs automatically
2. Takes data from `activities_combined` view
3. View combines:
   - `activities_raw_daily` (recent data)
   - `activities_raw_final_batch` (historical data)
4. Overwrites `activities_data` table with fresh data

### Managing Scheduled Queries

#### In BigQuery Console
1. Go to **BigQuery → Scheduled queries**
2. View execution history and status
3. See successful runs (green checkmarks in image)
4. Click "View details" for specific run information

#### Key Settings
- **Repeat frequency**: 1 hour
- **Start date and run time**: Set to start immediately
- **End**: Never (runs indefinitely)
- **Destination**: `data-etl-to-bigquery.ctm_data.activities_data`
- **Write preference**: Overwrite table

## Schedule Flow

### Daily Data Flow
```
12:00 AM UTC → Accounts Sync → Updates ctm_data.accounts
     ↓
12:00 AM UTC → Activities Sync → Updates ctm_data.activities_raw_daily
     ↓
Every Hour → Scheduled Query → Updates ctm_data.activities_data
```

### Why These Times?
- **12:00 AM UTC**: Accounts update first (metadata needed for activities)
- **12:00 AM UTC**: Activities sync runs after Cloud Scheduler triggers the accounts sync; the daily job reads the latest available `ctm_data.accounts`
- **Hourly processing**: Ensures fresh combined data for reporting

## Monitoring Schedules

### Check Schedule Status
Based on the Cloud Scheduler image:
- Both schedules show "Enabled" status
- Last run times are visible
- Next run times are calculated automatically

### Execution History
The BigQuery scheduled query image shows:
- Multiple successful executions (green checkmarks)
- Consistent hourly runs
- All queries completed successfully

### Common Schedule Issues

#### Schedule Not Running
- Check if schedule is "Enabled"
- Verify target Cloud Run job exists
- Check service account permissions

#### Failed Executions
- Review Cloud Run job logs
- Check BigQuery scheduled query errors
- Verify API credentials and quotas

## Time Zones

### Current Setup
- All schedules use **UTC timezone**
- Accounts: 12:00 AM UTC = 8:00 PM EST (previous day during standard time)
- Activities: 12:00 AM UTC = 8:00 PM EST (previous day during standard time)

### Changing Timezone
```bash
# Change to Eastern Time
gcloud scheduler jobs update http ctm-accounts-sync-daily-schedule \
    --time-zone="America/New_York" \
    --location=us-central1
```

## Best Practices

### Schedule Timing
- Avoid peak CTM API usage times
- Space out jobs to prevent resource conflicts
- Consider your business reporting needs

### Monitoring
- Set up alerts for schedule failures
- Monitor job execution times
- Check data freshness regularly

### Maintenance
- Review schedules monthly
- Update schedules when changing business requirements
- Test schedule changes in development first
