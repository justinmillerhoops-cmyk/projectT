from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st
import toml

from compute.probability import event_cutlines, score_probability
from compute.rankings import rank_by_event, season_best
from compute.scoring import projected_team_scoring
from ingest.html_extract import extract_tables_from_html
from ingest.normalize import normalize_tables
from ingest.scanner import load_classifications, save_classifications, scan_folder
from ingest.schema import FileClassification
from reporting.email_tools import build_mailto, send_email_smtp
from reporting.pdf_export import export_pdf_report
from storage import load_cache, read_recent_audits, read_state, save_cache, write_audit, write_state

CONFIG = toml.load("config.toml")
DATA_DIR = Path(CONFIG["app"]["data_folder"])
CLASS_FILE = Path("data/classifications.json")


@st.cache_data(show_spinner=False)
def load_cached(name: str) -> pd.DataFrame:
    return load_cache(name)


def compute_coverage(df: pd.DataFrame) -> dict:
    if df.empty:
        return {}
    return {
        "seasons": sorted(df["season"].dropna().unique().tolist()),
        "genders": sorted(df["gender"].dropna().unique().tolist()),
        "scopes": sorted(df["scope"].dropna().unique().tolist()),
        "years": sorted(pd.to_datetime(df["file_modified_at"]).dt.year.dropna().unique().astype(int).tolist()),
    }


def do_refresh() -> tuple[bool, str]:
    scanned = scan_folder(DATA_DIR, CLASS_FILE)
    warnings = []
    all_rows = []
    for sf in scanned:
        if sf.classification is None:
            warnings.append(f"unclassified:{sf.path.name}")
            continue
        if sf.path.suffix.lower() != ".html":
            warnings.append(f"unsupported_file_type:{sf.path.name}")
            continue
        tables = extract_tables_from_html(sf.path)
        rows = normalize_tables(tables, sf.classification, sf.path, datetime.utcfromtimestamp(sf.modified_ts))
        all_rows.extend([r.model_dump() for r in rows])

    df = pd.DataFrame(all_rows)
    if df.empty:
        write_audit(len(scanned), 0, warnings + ["no_rows"], {s.path.name: s.file_hash for s in scanned})
        return False, "No valid rows ingested; last-good cache retained."

    df["year"] = pd.to_datetime(df["meet_date"], errors="coerce").dt.year
    sb = season_best(df)
    ranked = rank_by_event(sb)
    conf = ranked[ranked["scope"] == "BIGEAST"]
    nat = ranked[ranked["scope"].isin(["NCAA_INDOOR_QUAL", "NCAA_OUTDOOR_EAST_QUAL"])]
    confmeet = df[df["scope"] == "confmeet_BIGEAST"]
    cut = event_cutlines(confmeet)
    prob = score_probability(conf, cut)
    team_totals, event_scores, who_scores = projected_team_scoring(conf)

    save_cache("raw", df)
    save_cache("season_best", sb)
    save_cache("ranked", ranked)
    save_cache("conf_ranked", conf)
    save_cache("nat_ranked", nat)
    save_cache("cutlines", cut)
    save_cache("probability", prob)
    save_cache("team_totals", team_totals)
    save_cache("event_scores", event_scores)
    save_cache("who_scores", who_scores)

    newest = max(datetime.utcfromtimestamp(s.modified_ts) for s in scanned).isoformat() if scanned else None
    coverage = compute_coverage(df)
    write_state(newest, datetime.utcnow().isoformat(), coverage)
    write_audit(len(scanned), len(df), warnings, {s.path.name: s.file_hash for s in scanned})
    load_cached.clear()
    return True, f"Refresh complete: {len(df)} rows."




def render_admin_uploads(data_dir: Path) -> None:
    st.subheader("Admin Uploads (for Streamlit-hosted use)")
    st.caption("Upload HTML/CSV exports here when running on Streamlit Cloud. Files are saved into app.data_folder.")
    uploads = st.file_uploader(
        "Upload ranking exports",
        type=["html", "csv"],
        accept_multiple_files=True,
        key="admin_uploads",
    )
    if uploads:
        data_dir.mkdir(parents=True, exist_ok=True)
        saved = 0
        for up in uploads:
            target = data_dir / up.name
            target.write_bytes(up.getbuffer())
            saved += 1
        st.success(f"Saved {saved} file(s) to {data_dir}.")

def render_unclassified():
    st.subheader("Unclassified Files")
    scanned = scan_folder(DATA_DIR, CLASS_FILE)
    unclassified = [s for s in scanned if s.classification is None]
    if not unclassified:
        st.success("No unclassified files.")
        return

    existing = load_classifications(CLASS_FILE)
    for sf in unclassified:
        st.markdown(f"**{sf.path.name}** (`{sf.file_hash[:10]}`)")
        c1, c2, c3, c4, c5 = st.columns(5)
        file_type = c1.selectbox("Type", ["current", "confmeet"], key=f"ft-{sf.file_hash}")
        season = c2.selectbox("Season", ["indoor", "outdoor"], key=f"sn-{sf.file_hash}")
        gender = c3.selectbox("Gender", ["M", "F", "BOTH"], key=f"gn-{sf.file_hash}")
        scope = c4.text_input("Scope", value="BIGEAST", key=f"sc-{sf.file_hash}")
        dt = c5.text_input("Date or Year", value="2026-01-01", key=f"dt-{sf.file_hash}")
        if st.button("Save classification", key=f"save-{sf.file_hash}"):
            payload = {
                "file_type": file_type,
                "season": season,
                "gender": gender,
                "scope": scope,
                "date": None,
                "year": None,
            }
            if file_type == "current":
                payload["date"] = dt
            else:
                payload["scope"] = "confmeet_BIGEAST"
                payload["year"] = int(dt)
            existing[sf.file_hash] = payload
            save_classifications(CLASS_FILE, existing)
            st.success("Saved.")


def main():
    st.set_page_config(layout="wide", page_title="Villanova TFRRS Tool")
    st.title("Villanova Track & Field Rankings & Projections")

    if CONFIG["app"].get("viewer_password"):
        pw = st.sidebar.text_input("Viewer password", type="password")
        if pw != CONFIG["app"]["viewer_password"]:
            st.stop()

    tabs = st.tabs([
        "Refresh & Status",
        "BIG EAST Rankings",
        "National Rankings",
        "Projected BIG EAST Team Score",
        "Score Probability",
        "Data Issues",
        "Settings",
    ])

    with tabs[0]:
        state = read_state()
        st.metric("Last data added", state.get("last_data_added") or "N/A")
        st.metric("Last successful refresh", state.get("last_successful_refresh") or "N/A")
        st.json(state.get("coverage", {}))
        if st.button("Refresh Data", type="primary"):
            ok, msg = do_refresh()
            (st.success if ok else st.error)(msg)
        audits = pd.DataFrame(read_recent_audits(20))
        st.subheader("Ingest Audit Log")
        st.dataframe(audits, use_container_width=True)
        render_admin_uploads(DATA_DIR)
        render_unclassified()

    conf = load_cached("conf_ranked")
    nat = load_cached("nat_ranked")
    team_totals = load_cached("team_totals")
    event_scores = load_cached("event_scores")
    who_scores = load_cached("who_scores")
    prob = load_cached("probability")
    cut = load_cached("cutlines")
    raw = load_cached("raw")

    with tabs[1]:
        s = st.selectbox("Season", ["indoor", "outdoor"], key="be_season")
        g = st.selectbox("Gender", ["M", "F"], key="be_gender")
        q = st.text_input("Search athlete/team")
        view = conf[(conf["season"] == s) & (conf["gender"] == g)] if not conf.empty else conf
        if q and not view.empty:
            view = view[view["athlete_name"].str.contains(q, case=False) | view["team"].str.contains(q, case=False)]
        st.dataframe(view.sort_values(["event", "rank"]) if not view.empty else view, use_container_width=True)
        st.download_button("Export CSV", data=view.to_csv(index=False), file_name="big_east_rankings.csv")

    with tabs[2]:
        s = st.selectbox("Season", ["indoor", "outdoor"], key="nat_season")
        g = st.selectbox("Gender", ["M", "F"], key="nat_gender")
        view = nat[(nat["season"] == s) & (nat["gender"] == g)] if not nat.empty else nat
        st.dataframe(view.sort_values(["event", "rank"]) if not view.empty else view, use_container_width=True)
        st.download_button("Export CSV", data=view.to_csv(index=False), file_name="national_rankings.csv")

    with tabs[3]:
        st.dataframe(team_totals, use_container_width=True)
        st.subheader("Points by Event")
        st.dataframe(event_scores, use_container_width=True)
        st.subheader("Who Scores")
        st.dataframe(who_scores, use_container_width=True)

    with tabs[4]:
        st.dataframe(prob, use_container_width=True)
        st.subheader("5-Year Cutlines")
        st.dataframe(cut.sort_values(["event", "year"]) if not cut.empty else cut, use_container_width=True)

    with tabs[5]:
        if raw.empty:
            st.info("No data")
        else:
            issues = raw[raw["confidence"] == "LOW"]
            st.dataframe(issues[["athlete_name", "team", "event", "mark_raw", "issues", "source_file"]], use_container_width=True)

    with tabs[6]:
        st.write("Coach emails:", ", ".join(CONFIG["app"].get("coach_emails", [])))
        st.write("Scoring places default:", CONFIG["app"].get("scoring_places", 8))

        if st.button("Generate PDF Report"):
            out = export_pdf_report(Path("data/report.pdf"), team_totals, conf, prob, read_state().get("coverage", {}))
            st.success(f"Created: {out}")

        if st.button("Email Coaches"):
            report_path = Path("data/report.pdf")
            subject = "Villanova T&F Weekly Rankings Report"
            body = f"Automated report generated. PDF path: {report_path.resolve()}\nNote: mailto links do not auto-attach files."
            mailto = build_mailto(CONFIG["app"].get("coach_emails", []), subject, body)
            st.markdown(f"[Open email client]({mailto})")

            smtp_cfg = CONFIG.get("smtp", {})
            required = ["host", "port", "username", "password"]
            if all(smtp_cfg.get(k) for k in required):
                try:
                    send_email_smtp(
                        smtp_cfg["host"],
                        int(smtp_cfg["port"]),
                        smtp_cfg["username"],
                        smtp_cfg["password"],
                        CONFIG["app"].get("coach_emails", []),
                        subject,
                        body,
                        report_path if report_path.exists() else None,
                    )
                    st.success("SMTP email sent.")
                except Exception as e:
                    st.error(f"SMTP failed: {e}")


if __name__ == "__main__":
    main()
