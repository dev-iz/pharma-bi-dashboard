
import requests
import pandas as pd
import re
from pathlib import Path

OUT_DIR = Path('data_raw')
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_FILE = OUT_DIR / 'partd_by_provider_drug_2022.csv'

CATALOG_URL = 'https://catalog.data.gov/dataset/medicare-part-d-prescribers-by-provider-and-drug-ad73e'
LANDING_URL = ('https://data.cms.gov/provider-summary-by-type-of-service/'
               'medicare-part-d-prescribers/medicare-part-d-prescribers-by-provider-and-drug')

def download_from_catalog() -> bool:
    try:
        r = requests.get(CATALOG_URL, timeout=30)
        r.raise_for_status()
    except Exception as e:
        print('Catalog request failed:', e)
        return False
    matches = re.findall(r'href="(https?://[^"]*MUP_DPR_[^"]*_DY22_NPIBN\.csv)"', r.text, flags=re.IGNORECASE)
    if not matches:
        print('No DY22 CSV link found on catalog page.')
        return False
    csv_url = matches[0]
    print('Found distribution:', csv_url)
    try:
        with requests.get(csv_url, stream=True, timeout=120) as resp:
            resp.raise_for_status()
            with open(OUTPUT_FILE, 'wb') as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
        return True
    except Exception as e:
        print('Direct download failed:', e)
        return False

def discover_uuid_from_landing() -> str | None:
    try:
        r = requests.get(LANDING_URL, timeout=30)
        r.raise_for_status()
    except Exception as e:
        print('Landing request failed:', e)
        return None
    m = re.search(r'data-api/v1/dataset/([a-f0-9-]+)/data', r.text, flags=re.IGNORECASE)
    return m.group(1) if m else None

def download_via_api() -> bool:
    uuid = discover_uuid_from_landing()
    if not uuid:
        print('Dataset UUID not found. Cannot use API fallback.')
        return False
    print('Using dataset UUID:', uuid)
    cols = 'NPI,BRAND_NAME,GENERIC_NAME,TOTAL_CLAIM_COUNT,TOTAL_DRUG_COST,BENE_COUNT,YEAR'
    offset, size = 0, 5000
    frames = []
    while True:
        url = f'https://data.cms.gov/data-api/v1/dataset/{uuid}/data'
        params = {'size': size, 'offset': offset, 'filter[YEAR]': '2022', 'column': cols}
        resp = requests.get(url, params=params, timeout=60)
        if resp.status_code != 200:
            print('API request failed', resp.status_code, resp.text[:200])
            return False
        data = resp.json()
        if not data:
            break
        frames.append(pd.DataFrame(data))
        offset += size
        if len(data) < size:
            break
    if not frames:
        print('No data retrieved from API.')
        return False
    df = pd.concat(frames, ignore_index=True)
    df.to_csv(OUTPUT_FILE, index=False)
    return True

def safe_head_count(path: Path, sample_rows: int = 10):
    df_sample = pd.read_csv(path, nrows=sample_rows)
    with open(path, 'rb') as f:
        row_count = sum(buf.count(b'\n') for buf in iter(lambda: f.read(1024*1024), b'')) - 1
    print('Path:', str(path))
    print('Size (bytes):', path.stat().st_size)
    print('Columns:', list(df_sample.columns))
    print('Row count:', max(row_count, 0))
    print('Sample:')
    print(df_sample)

def main():
    if OUTPUT_FILE.exists():
        print('File already exists, skipping download.')
        safe_head_count(OUTPUT_FILE)
        return
    success = download_from_catalog()
    if not success:
        print('Falling back to Provider Data Catalog API…')
        success = download_via_api()
    if success:
        safe_head_count(OUTPUT_FILE)
    else:
        print('Both distribution discovery and API fallback failed.')

if __name__ == '__main__':
    main()
