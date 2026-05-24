import base64
import requests
import pandas as pd
from pandas_gbq import to_gbq
from google.cloud import bigquery
import re
import time
import json
import datetime
import os
import sys
import logging
import uuid
from google.auth import default
from dotenv import load_dotenv
from ctm_custom_fields import enrich_call_custom_fields

# Load environment variables
load_dotenv()
# -------------------------
# Logging setup for Cloud Run
# -------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# -------------------------
# Configuration - Get from environment variables
# -------------------------
def get_env_var(var_name, required=True):
    """Get environment variable with optional requirement check"""
    value = os.environ.get(var_name)
    if required and not value:
        logger.error(f"Required environment variable {var_name} is not set")
        sys.exit(1)
    return value

def get_int_env_var(var_name, default):
    value = get_env_var(var_name, required=False)
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError:
        logger.error(f"Environment variable {var_name} must be an integer, got {value!r}")
        sys.exit(1)

def get_bool_env_var(var_name, default=False):
    value = get_env_var(var_name, required=False)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "t", "yes", "y"}

# CTM API credentials from environment variables (Secret Manager)
access_key = get_env_var('CTM_ACCESS_KEY')
secret_key = get_env_var('CTM_SECRET_KEY')

# BigQuery config
project_id = get_env_var('PROJECT_ID', required=False) or 'data-etl-to-bigquery'
dataset_id = 'ctm_data'
raw_table_id = get_env_var('RAW_TABLE_ID', required=False) or 'activities_raw_daily'
destination_table = f"{dataset_id}.{raw_table_id}"

# Sync window config. Defaults preserve the existing "yesterday only" job.
lookback_days = get_int_env_var('LOOKBACK_DAYS', 1)
end_date_offset_days = get_int_env_var('END_DATE_OFFSET_DAYS', 1)
include_sync_metadata = get_bool_env_var('INCLUDE_SYNC_METADATA', False)
sync_mode = get_env_var('SYNC_MODE', required=False) or 'daily'

if lookback_days < 1:
    logger.error("LOOKBACK_DAYS must be at least 1")
    sys.exit(1)

if end_date_offset_days < 0:
    logger.error("END_DATE_OFFSET_DAYS must be at least 0")
    sys.exit(1)

# Basic Auth header
auth_string = f"{access_key}:{secret_key}"
auth_bytes = auth_string.encode('ascii')
auth_b64 = base64.b64encode(auth_bytes).decode('ascii')
headers = {
    'Authorization': f'Basic {auth_b64}',
    'Content-Type': 'application/json'
}

# Rate limit config
REQUESTS_PER_SECOND = 8
SLEEP_SECONDS = 1.0 / REQUESTS_PER_SECOND

# -------------------------
# Auth and Client Setup
# -------------------------
credentials, _ = default()
bq_client = bigquery.Client(project=project_id, credentials=credentials)

# -------------------------
# Helper Functions
# -------------------------
def get_sync_date_window(reference_time=None):
    reference_time = reference_time or datetime.datetime.utcnow()
    end_date = reference_time.date() - datetime.timedelta(days=end_date_offset_days)
    start_date = end_date - datetime.timedelta(days=lookback_days - 1)
    return start_date, end_date

def standardize_dataframe_schema(df, target_table_project, target_table_dataset, target_table_name):
    """
    Standardize DataFrame schema to match target BigQuery table
    """
    try:
        # Get target table schema
        table_ref = f"{target_table_project}.{target_table_dataset}.{target_table_name}"
        table = bq_client.get_table(table_ref)
        
        # Get all expected columns from target table
        expected_columns = {field.name: field.field_type for field in table.schema}
        logger.info(f"Target table has {len(expected_columns)} columns")
        logger.info(f"Current DataFrame has {len(df.columns)} columns")
        
        # Add missing columns with appropriate default values
        missing_columns = set(expected_columns.keys()) - set(df.columns)
        if missing_columns:
            logger.info(f"Adding {len(missing_columns)} missing columns: {missing_columns}")
            for col in missing_columns:
                field_type = expected_columns[col]
                # Set default values based on BigQuery field type
                if field_type in ['STRING', 'TEXT']:
                    df[col] = None  # Will become NULL in BigQuery
                elif field_type in ['INTEGER', 'INT64']:
                    df[col] = None
                elif field_type in ['FLOAT', 'FLOAT64', 'NUMERIC']:
                    df[col] = None
                elif field_type in ['BOOLEAN', 'BOOL']:
                    df[col] = None
                elif field_type in ['TIMESTAMP', 'DATETIME', 'DATE', 'TIME']:
                    df[col] = None
                else:
                    df[col] = None  # Default to NULL for unknown types
        
        # Remove columns that don't exist in target table
        extra_columns = set(df.columns) - set(expected_columns.keys())
        if extra_columns:
            logger.info(f"Removing {len(extra_columns)} extra columns: {extra_columns}")
            df = df.drop(columns=list(extra_columns))
        
        # Reorder columns to match target table order
        target_column_order = [field.name for field in table.schema]
        df = df[target_column_order]
        
        logger.info(f"✅ Schema standardized: {len(df.columns)} columns")
        return df
        
    except Exception as e:
        logger.error(f"❌ Error standardizing schema: {str(e)}")
        return df

def fetch_all_calls_for_account(account_id, start_date, end_date):
    """Fetch all calls for a specific account"""
    base_url = f'https://api.calltrackingmetrics.com/api/v1/accounts/{account_id}/calls'
    all_calls = []
    url = base_url

    params = {
        'per_page': 100,
        'start_date': start_date.strftime('%Y-%m-%d'),
        'end_date': end_date.strftime('%Y-%m-%d')
    }

    while url:
        logger.info(f"Fetching calls for account {account_id}: {url} with params {params}")
        response = requests.get(url, headers=headers, params=params)
        if response.status_code != 200:
            raise Exception(f"Error fetching data for account {account_id}: {response.status_code} {response.text}")
        data = response.json()
        all_calls.extend(data.get('calls', []))
        url = data.get('next_page')
        params = None  # Next page URL includes all params already
        time.sleep(SLEEP_SECONDS)

    return all_calls

def get_active_accounts():
    """Get active accounts from BigQuery"""
    query = f"""
        SELECT id, name
        FROM `{project_id}.{dataset_id}.accounts`
    """
    results = bq_client.query(query).result()
    return [(row.id, row.name) for row in results]

def clean_column_name(col):
    """Clean column names for BigQuery compatibility"""
    col = re.sub(r'[^a-zA-Z0-9_]', '_', col)
    if not re.match(r'^[a-zA-Z_]', col):
        col = '_' + col
    return col.lower()

# -------------------------
# Main Job Function
# -------------------------
def main():
    start_time = datetime.datetime.now()
    sync_window_start, sync_window_end = get_sync_date_window()
    sync_loaded_at = datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    sync_run_id = (
        get_env_var('CLOUD_RUN_EXECUTION', required=False)
        or f"{sync_mode}-{datetime.datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    )
    
    # Log job start with structured logging
    logger.info("JOB_START: CTM Daily Sync job initiated", extra={
        'job_name': 'ctm_daily_sync',
        'status': 'STARTED',
        'timestamp': start_time.isoformat()
    })

    try:
        logger.info("🚀 CTM Daily Sync job starting...")
        logger.info(
            "Sync config: mode=%s destination=%s lookback_days=%s start_date=%s end_date=%s metadata=%s",
            sync_mode,
            destination_table,
            lookback_days,
            sync_window_start,
            sync_window_end,
            include_sync_metadata,
        )
        
        # Get active accounts
        accounts = get_active_accounts()
        logger.info(f"Found {len(accounts)} active accounts")

        all_calls = []
        accounts_processed = 0
        
        # Process each account
        for account_id, account_name in accounts:
            logger.info(f"Processing account {account_id} - {account_name}")
            calls = fetch_all_calls_for_account(account_id, sync_window_start, sync_window_end)

            # Add account info to each call
            for call in calls:
                enrich_call_custom_fields(call)
                call['account_id'] = account_id
                call['account_name'] = account_name
                if include_sync_metadata:
                    call['ctm_sync_loaded_at'] = sync_loaded_at
                    call['ctm_sync_run_id'] = sync_run_id
                    call['ctm_sync_window_start'] = sync_window_start.isoformat()
                    call['ctm_sync_window_end'] = sync_window_end.isoformat()
                    call['ctm_sync_lookback_days'] = lookback_days

                # Convert nested objects/lists to JSON string to avoid schema errors
                for k, v in call.items():
                    if isinstance(v, (dict, list)):
                        call[k] = json.dumps(v)

            all_calls.extend(calls)
            accounts_processed += 1
            logger.info(f"Account {account_id} processed: {len(calls)} calls")

        logger.info(f"Total calls fetched: {len(all_calls)}")

        if not all_calls:
            logger.info("⚠️ No calls fetched, job completed with no data to process.")
            
            # Log successful completion with zero data
            end_time = datetime.datetime.now()
            processing_time = (end_time - start_time).total_seconds()
            
            logger.info("JOB_SUCCESS: CTM Daily Sync completed successfully (no data)", extra={
                'job_name': 'ctm_daily_sync',
                'status': 'SUCCESS',
                'total_accounts_processed': accounts_processed,
                'total_calls_fetched': 0,
                'processing_time_seconds': round(processing_time, 2),
                'timestamp': end_time.isoformat()
            })
            return

        # Create DataFrame from normalized JSON
        df = pd.json_normalize(all_calls)

        # Convert timestamps (if present)
        for date_col in ['called_at', 'billed_at', 'ctm_sync_loaded_at']:
            if date_col in df.columns:
                df[date_col] = pd.to_datetime(df[date_col], errors='coerce', utc=True)

        # Clean columns for BigQuery
        df.columns = [clean_column_name(c) for c in df.columns]

        logger.info(f"DataFrame shape before standardization: {df.shape}")
        
        # Standardize schema before upload
        df = standardize_dataframe_schema(df, project_id, dataset_id, raw_table_id)
        
        logger.info(f"DataFrame shape after standardization: {df.shape}")
        logger.info("Sample of standardized data:")
        logger.info(df.head(2).to_string())

        # Upload to BigQuery
        to_gbq(df, destination_table, project_id=project_id, if_exists='append')
        logger.info(f"✅ Data uploaded to {destination_table}")

        # Calculate processing time
        end_time = datetime.datetime.now()
        processing_time = (end_time - start_time).total_seconds()

        # Log successful completion
        logger.info("JOB_SUCCESS: CTM Daily Sync completed successfully", extra={
            'job_name': 'ctm_daily_sync',
            'status': 'SUCCESS',
            'total_accounts_processed': accounts_processed,
            'total_calls_fetched': len(all_calls),
            'dataframe_rows': len(df),
            'dataframe_columns': len(df.columns),
            'processing_time_seconds': round(processing_time, 2),
            'timestamp': end_time.isoformat()
        })

    except Exception as e:
        end_time = datetime.datetime.now()
        processing_time = (end_time - start_time).total_seconds()
        
        # Log failure
        logger.error("JOB_FAILURE: CTM Daily Sync failed", extra={
            'job_name': 'ctm_daily_sync',
            'status': 'FAILED',
            'error_message': str(e),
            'processing_time_seconds': round(processing_time, 2),
            'timestamp': end_time.isoformat()
        }, exc_info=True)
        
        # Re-raise so Cloud Run marks job as failed
        raise

if __name__ == '__main__':
    main()
