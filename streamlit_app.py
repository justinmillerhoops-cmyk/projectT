"""
Streamlit Cloud entry point.

Streamlit Cloud runs from the repo root, but the actual app lives at
villanova_tf/app.py. runpy.run_path executes that file with __file__
set correctly, so all relative path lookups inside app.py (config.yaml,
data/, etc.) resolve to the right locations.

In Streamlit Cloud: set the "Main file path" to streamlit_app.py.
Locally you can also run this directly:
    streamlit run streamlit_app.py
or run the app module directly:
    streamlit run villanova_tf/app.py
"""
import runpy
import sys
from pathlib import Path

_root = Path(__file__).parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

runpy.run_path(str(_root / "villanova_tf" / "app.py"), run_name="__main__")
