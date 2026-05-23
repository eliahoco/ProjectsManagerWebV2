"""Unit tests for urgency_classifier — CB-2914 E6."""
from services.urgency_classifier import classify, labels_to_string


def test_production_down_critical():
    r = classify("Production is down — all users seeing 500 errors")
    assert r.priority == "CRITICAL"
    assert "production-down" in r.labels
    assert "scope-all-users" in r.labels
    assert any("production-down" in tag for tag in r.rationale)


def test_data_loss_critical():
    r = classify("We lost user records after the migration")
    assert r.priority in ("HIGH", "CRITICAL")
    assert "data-loss" in r.labels


def test_security_surface_bumps_severity():
    r = classify("CSRF token validation might be missing on the upload endpoint")
    assert r.priority in ("MEDIUM", "HIGH")
    assert "security" in r.labels


def test_cosmetic_with_workaround_low():
    r = classify("Minor cosmetic spacing issue on the settings page; workaround: refresh")
    assert r.priority == "LOW"
    assert "cosmetic" in r.labels
    assert "has-workaround" in r.labels


def test_single_user_reduces_scope():
    r = classify("Only happens for one user, just on their account")
    assert r.priority == "LOW"


def test_stack_layer_labels_pure_classification():
    r = classify("React component re-renders too aggressively in the frontend")
    assert "frontend" in r.labels
    assert "performance" in r.labels


def test_multi_tenant_security_compounds():
    r = classify("Cross-tenant data leak in multi-tenant API — security audit failed")
    assert r.priority == "CRITICAL"
    assert "security" in r.labels
    assert "multi-tenant" in r.labels


def test_empty_description_low():
    r = classify("")
    assert r.priority == "LOW"
    assert r.labels == []


def test_evidence_text_factored_in():
    r = classify("Bug", evidence={"stack": "production-down, data-loss in users table"})
    assert r.priority in ("HIGH", "CRITICAL")


def test_labels_to_string_sorted_unique():
    assert labels_to_string(["frontend", "security", "frontend", "backend"]) == "backend,frontend,security"


def test_method_is_rubric():
    r = classify("anything")
    assert r.method == "rubric"
