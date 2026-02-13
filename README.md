# Villanova T&F Rankings Tool (Streamlit)

Deterministic Streamlit app for BIG EAST and NCAA ranking/scoring workflows. No web fetching and no LLM usage.

## Admin workflow (Google Drive synced folder)

1. Save/Export ranking pages as HTML.
2. Drop files into `data/input` (or change `app.data_folder` in `config.toml`).
3. Preferred naming:
   - `current__{season}__{gender}__{scope}__{date}__.html`
   - `confmeet__BIGEAST__{season}__{year}__.html`
4. Open app and click **Refresh Data**.

## Running

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Ingestion modes

- **Mode A (strict filename schema):** auto-classified by filename pattern.
- **Mode B (fallback labeling UI):** unknown files appear in **Refresh & Status → Unclassified Files**.
  - Label once, then mapping is stored in `data/classifications.json` keyed by file hash.

## What the app provides

1. BIG EAST conference rankings by event (season best)
2. National rankings from uploaded NCAA qualification list files
3. Projected BIG EAST team scoring (10-8-6-5-4-3-2-1) with entry limits (4 individuals / 1 relay per team-event)
4. Score probability vs last 5 years of BIG EAST 8th-place cutlines, plus bubble distance
5. Data freshness: last data added, last successful refresh, coverage summary, ingest audit log
6. LOW confidence issue table

## LOW confidence meaning

Rows are labeled `LOW` when data is incomplete/ambiguous/unparseable, such as:
- invalid outcomes (`DNS`, `DNF`, `FOUL`, `NM`, `NH`, `NT`)
- unparseable mark strings
- missing/invalid wind for wind-applicable events
- wind-illegal marks (> +2.0)
- unknown event configuration (event not in deterministic `EVENT_CONFIG`)

The app never guesses missing values; it preserves provenance and flags issues.

## Caching and safety

- Last-good datasets are saved to `data/cache/*.parquet`.
- If refresh fails, previous cache remains usable.
- Every ingest writes an audit file in `data/audit/{timestamp}.json`.

## Troubleshooting

- **No data after refresh**: ensure HTML tables include athlete/team/event/mark columns.
- **Files unclassified**: use the labeling controls in the first tab.
- **Unknown events flagged LOW**: add exact event name to `compute/marks.py` `EVENT_CONFIG`.
- **PDF export fails**: ensure `reportlab` is installed.
- **SMTP fails**: verify `config.toml` SMTP host/port/credentials; mailto still works without SMTP.
