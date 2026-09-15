"""The machine-readable CLI contract (v0.5).

Non-Python clients assert against `neuraxis contract` instead of keeping their
own copy of the exit-code table. These tests make sure the contract cannot
drift from the code it describes — if it could, the clients that trust it would
drift too, silently.
"""

from __future__ import annotations

import json

from neuraxis import __version__
from neuraxis.cli import EXIT_BY_DECISION, EXIT_ERROR, EXIT_OK, main
from neuraxis.model import (
    REQUEST_OPTIONAL_FIELDS,
    REQUEST_REQUIRED_FIELDS,
    AuthorityRequest,
    Decision,
    Obligation,
    Risk,
)


def _contract(capsys) -> dict:
    assert main(["--json", "contract"]) == EXIT_OK
    return json.loads(capsys.readouterr().out)


def test_contract_lists_every_decision(capsys):
    contract = _contract(capsys)
    assert set(contract["decisions"]) == {d.value for d in Decision}


def test_contract_exit_codes_match_the_dispatch_table(capsys):
    """The published table and the table the CLI actually uses are one table."""
    contract = _contract(capsys)
    assert contract["decisions"] == {d.value: EXIT_BY_DECISION[d] for d in Decision}


def test_every_decision_has_a_distinct_exit_code(capsys):
    codes = list(_contract(capsys)["decisions"].values())
    assert len(codes) == len(set(codes)), "two decisions sharing an exit code are indistinguishable"


def test_only_allow_permits_and_only_allow_exits_zero(capsys):
    contract = _contract(capsys)
    assert contract["permitting_decisions"] == ["ALLOW"]
    assert contract["decisions"]["ALLOW"] == 0
    for name, code in contract["decisions"].items():
        if name != "ALLOW":
            assert code != 0, f"{name} exits 0, so a caller testing for zero would act on it"


def test_error_exit_is_not_a_decision_code(capsys):
    """A CLI fault must not be mistakable for a verdict."""
    contract = _contract(capsys)
    assert contract["error_exit"] == EXIT_ERROR
    assert EXIT_ERROR not in contract["decisions"].values()


def test_contract_reports_request_fields_the_parser_actually_accepts(capsys):
    contract = _contract(capsys)
    assert contract["request_fields"]["required"] == list(REQUEST_REQUIRED_FIELDS)
    assert contract["request_fields"]["optional"] == list(REQUEST_OPTIONAL_FIELDS)

    # Every advertised field must parse, or the contract is lying to clients.
    payload = {
        "intent": "i", "identity": "a", "role": "operator", "capability": "IL-01",
        "scope": "s", "risk": "LOW", "performer": "a", "verifier": "b",
        "rollback_tested": True, "ratification_ref": "BADF-1",
    }
    assert set(payload) == set(REQUEST_REQUIRED_FIELDS) | set(REQUEST_OPTIONAL_FIELDS)
    AuthorityRequest.from_dict(payload)


def test_contract_lists_obligations_and_risks(capsys):
    contract = _contract(capsys)
    assert set(contract["obligations"]) == {o.value for o in Obligation}
    assert set(contract["risks"]) == {r.value for r in Risk}


def test_contract_reports_the_package_version(capsys):
    assert _contract(capsys)["version"] == __version__


def test_contract_text_output_marks_the_permitting_decision(capsys):
    assert main(["contract"]) == EXIT_OK
    out = capsys.readouterr().out
    assert "the only permitting decision" in out
    assert out.count("the only permitting decision") == 1
