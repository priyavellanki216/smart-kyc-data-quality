from pathlib import Path
import py_compile


def test_streamlit_entry_compiles():
    app_path = Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py"
    py_compile.compile(str(app_path), doraise=True)
    assert app_path.is_file()


def test_all_streamlit_workspace_views_run(monkeypatch, tmp_path):
    from streamlit.testing.v1 import AppTest

    app_path = Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py"
    monkeypatch.setenv("KYC_DB_PATH", str(tmp_path / "streamlit-test.db"))
    app = AppTest.from_file(str(app_path), default_timeout=20).run()
    assert not app.exception
    for page in ["Review queue", "Client records", "Duplicate candidates", "Audit history", "Reporting & exports", "Operations overview"]:
        app.radio[0].set_value(page).run()
        assert not app.exception, f"{page}: {app.exception}"


def test_streamlit_review_form_persists_action_and_audit(monkeypatch, tmp_path):
    from streamlit.testing.v1 import AppTest
    from kyc_quality.database import audit_for_entity, read_table

    database = tmp_path / "streamlit-action.db"
    app_path = Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py"
    monkeypatch.setenv("KYC_DB_PATH", str(database))
    app = AppTest.from_file(str(app_path), default_timeout=20).run()
    app.radio[0].set_value("Review queue").run()
    case_id = app.selectbox[5].value
    app.text_input[1].set_value("QA Analyst")
    app.text_area[0].set_value("Synthetic test note: requested corrected corporate record.")
    app.form_submit_button[0].click().run()
    assert not app.exception
    actions = read_table(database, "review_actions", "case_id = ?", (case_id,))
    assert len(actions) == 1
    assert actions.iloc[0]["reviewer"] == "QA Analyst"
    events = audit_for_entity(database, "review_case", case_id)
    assert "Synthetic test note: requested corrected corporate record." in set(events["notes"])
