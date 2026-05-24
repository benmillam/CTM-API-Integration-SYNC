# CTM API Integration

## What the Code Does

Our Python ETL jobs connect to CallTrackingMetrics (CTM) API to extract call tracking data and load it into BigQuery for analysis.

### Job Functions

#### 1. Accounts Sync Job (`ctm-accounts-sync-job`)
**What it does:**
- Connects to CTM API every day at 12:00 AM UTC
- Downloads all account information 
- Cleans and formats the data
- Uploads to BigQuery `ctm_data.accounts` table

**Data collected:**
- Account names and IDs
- Contact information (phone, email)
- Account status and creation dates
- Metadata for linking with call activities

#### 2. Daily Activities Job (`ctm-daily-job`)
**What it does:**
- Runs daily at 12:00 AM UTC
- Fetches yesterday's call activities from CTM
- Processes call details (duration, source, outcome)
- Loads into BigQuery `ctm_data.activities_raw_daily` table

**Data collected:**
- Call details (start time, duration, caller ID)
- Tracking numbers and campaigns
- Call outcomes (answered, missed, etc.)
- Source attribution (Google Ads, website, etc.)
- Lead custom fields: `valid_lead`, `lead_summary`, and `is_spam`

#### 3. Batch Job (`ctm-batch-job`) 
**What it does:**
- **COMPLETED - Do not run again**
- Was used once to import historical data
- Created tables in `ctm_data_batch` dataset
- All historical data is now available

## How API Integration Works

### Authentication
Cloud Run Jobs receive `CTM_ACCESS_KEY` and `CTM_SECRET_KEY` from Google Secret Manager. Local `.env` files are only for local development and must not be uploaded to Cloud Build.

### Data Extraction Process
1. **Connect to CTM API** using your credentials
2. **Request data** in pages (100 records at a time)
3. **Handle rate limits** (max 1000 requests per hour)
4. **Process each page** until all data is collected
5. **Clean and validate** data before uploading
6. **Load to BigQuery** with proper error handling

### Error Handling
The code automatically handles:
- API rate limits (waits when hitting limits)
- Network timeouts (retries failed requests)
- Invalid data (skips bad records, logs issues)
- Authentication failures (clear error messages)

## Data Flow

### From CTM to BigQuery
```
CTM API → Python Job → Data Cleaning → BigQuery Tables
   ↓
Call Records → Format/Validate → activities_raw_daily
   ↓
Account Info → Clean/Structure → accounts
```

### Processing Pipeline
1. **Raw data** collected from CTM API
2. **Validation** ensures data quality
3. **Transformation** standardizes formats
4. **Loading** into appropriate BigQuery tables
5. **Logging** tracks success/failures

## API Endpoints Used

### Accounts Endpoint
- **URL**: `https://api.calltrackingmetrics.com/api/v1/accounts`
- **Purpose**: Get account master data
- **Frequency**: Daily (full refresh)

### Activities Endpoint  
- **URL**: `https://api.calltrackingmetrics.com/api/v1/accounts/{id}/calls`
- **Purpose**: Get call tracking activities
- **Frequency**: Daily (incremental)

## Data Transformations

### What the Code Cleans Up
- **Phone numbers**: Standardizes format (+1234567890)
- **Timestamps**: Converts to UTC timezone
- **Text fields**: Trims whitespace, handles nulls
- **Duplicates**: Removes duplicate records
- **Data types**: Ensures proper BigQuery types
- **Lead fields**: Recursively extracts `valid_lead`, `lead_summary`, and `is_spam` from call-level custom fields and account-specific nested contact or score objects before nested JSON is serialized

### Quality Checks
- Validates required fields exist
- Checks date ranges are logical
- Ensures phone numbers are valid format
- Logs any data quality issues

## Monitoring Job Performance

### Success Indicators
Based on the Cloud Run logs image, look for:
- **"JOB_SUCCESS"** messages
- **Record counts** (e.g., "323 accounts processed")
- **"Data successfully loaded to BigQuery"**
- **Processing time** under 5 minutes typically

### Log Messages to Watch
- `🚀 CTM Accounts sync job starting...`
- `📊 Fetching accounts from CTM API...`
- `✅ Uploading 323 account records to BigQuery table`
- `✅ Data successfully loaded to BigQuery`
- `JOB_SUCCESS: CTM Accounts sync completed successfully`

## Common API Issues

### Rate Limiting
- **Problem**: CTM limits to 1000 API calls per hour
- **Solution**: Code waits automatically when limits hit
- **Log message**: Shows "Rate limit exceeded, waiting..."

### Authentication Errors
- **Problem**: Invalid API credentials
- **Solution**: Check your `.env` file has correct keys
- **Log message**: "401 Unauthorized" errors

### Missing Data
- **Problem**: CTM API returns no data for date range
- **Solution**: Code logs warning but continues
- **Log message**: "No activities found for date range"

## API Configuration

### Current Settings
- **Batch size**: 100 records per API call (CTM maximum)
- **Timeout**: 30 seconds per request
- **Retries**: 3 attempts for failed calls
- **Rate limiting**: Automatic delays between calls

### Customizable Parameters
- Date ranges for activities (default: yesterday)
- Pagination size (fixed at 100 by CTM)
- Retry attempts and timeouts
- Account filtering (currently gets all accounts)

## Data Volume Expectations

### Typical Daily Loads
- **Accounts**: 300-500 records (full refresh)
- **Activities**: Varies by call volume (could be 0-10,000+ daily)
- **Processing time**: 2-5 minutes per job
- **API calls**: 10-50 calls per job typically

### Historical Batch Data
- **Total activities**: All historical call data
- **Stored in**: `ctm_data_batch` dataset  
- **Processing**: Completed, do not re-run batch job

## Integration Benefits

### Data Accessibility
- Call tracking data available in BigQuery for analysis
- Combines with other business data for reporting
- Real-time dashboard capabilities
- Historical trend analysis

### Automation
- No manual data exports needed
- Fresh data every day automatically
- Error monitoring and alerting
- Scalable processing as call volume grows
