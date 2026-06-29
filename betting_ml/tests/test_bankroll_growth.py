"""Tests for compute_bankroll_growth — the honest growth math.

Covers:
  • A deposit is NOT growth (balance = deposit → 0% growth)
  • A withdrawal is NOT a loss (netted out of the baseline)
  • Multi-book aggregation
  • No-deposit state (growth_pct = None)
  • Loss scenario
"""

import pytest

from app.backend.services.dynamo import compute_bankroll_growth


def test_empty_state():
    result = compute_bankroll_growth({}, [])
    assert result["overall"]["total_deposited"] == 0.0
    assert result["overall"]["growth_pct"] is None
    assert result["per_book"] == {}


def test_deposit_does_not_inflate_growth():
    """$500 deposited, balance still $500 → 0% growth."""
    accounts = {"BetMGM": {"current_balance": 500.0}}
    events = [
        {"book": "BetMGM", "type": "deposit", "amount": 500.0, "date": "2026-06-01", "event_id": "1"}
    ]
    result = compute_bankroll_growth(accounts, events)
    overall = result["overall"]
    assert overall["betting_pnl"] == pytest.approx(0.0)
    assert overall["growth_pct"] == pytest.approx(0.0)
    assert result["per_book"]["BetMGM"]["growth_pct"] == pytest.approx(0.0)


def test_honest_growth_after_winning():
    """$500 deposited, balance grew to $600 → 20% growth (= $100 / $500)."""
    accounts = {"BetMGM": {"current_balance": 600.0}}
    events = [
        {"book": "BetMGM", "type": "deposit", "amount": 500.0, "date": "2026-06-01", "event_id": "1"}
    ]
    result = compute_bankroll_growth(accounts, events)
    overall = result["overall"]
    assert overall["betting_pnl"] == pytest.approx(100.0)
    assert overall["growth_pct"] == pytest.approx(0.2)


def test_withdrawal_does_not_read_as_loss():
    """$500 deposit, win to $600, withdraw $100, balance $500.

    net_deposits = 500 - 100 = 400
    betting_pnl  = 500 - 400 = 100   ← withdrawal netted out; not a "loss"
    growth_pct   = 100 / 500  = 20%
    """
    accounts = {"BetMGM": {"current_balance": 500.0}}
    events = [
        {"book": "BetMGM", "type": "deposit", "amount": 500.0, "date": "2026-06-01", "event_id": "1"},
        {"book": "BetMGM", "type": "withdrawal", "amount": 100.0, "date": "2026-06-20", "event_id": "2"},
    ]
    result = compute_bankroll_growth(accounts, events)
    overall = result["overall"]
    assert overall["net_deposits"] == pytest.approx(400.0)
    assert overall["betting_pnl"] == pytest.approx(100.0)
    assert overall["growth_pct"] == pytest.approx(0.2)


def test_deposit_after_withdrawal_not_inflated():
    """$200 deposit, lose to $100, deposit $100 more, balance $200.

    total_deposited = 300, net_deposits = 300
    betting_pnl = 200 - 300 = -100; growth = -100/300 ≈ -33.3%
    """
    accounts = {"FanDuel": {"current_balance": 200.0}}
    events = [
        {"book": "FanDuel", "type": "deposit", "amount": 200.0, "date": "2026-06-01", "event_id": "1"},
        {"book": "FanDuel", "type": "deposit", "amount": 100.0, "date": "2026-06-10", "event_id": "2"},
    ]
    result = compute_bankroll_growth(accounts, events)
    overall = result["overall"]
    assert overall["total_deposited"] == pytest.approx(300.0)
    assert overall["net_deposits"] == pytest.approx(300.0)
    assert overall["betting_pnl"] == pytest.approx(-100.0)
    assert overall["growth_pct"] == pytest.approx(-100 / 300)


def test_multibook_aggregation():
    """Two books, each with $500 deposited; BetMGM up 20%, FanDuel down 10%."""
    accounts = {
        "BetMGM": {"current_balance": 600.0},
        "FanDuel": {"current_balance": 450.0},
    }
    events = [
        {"book": "BetMGM", "type": "deposit", "amount": 500.0, "date": "2026-06-01", "event_id": "1"},
        {"book": "FanDuel", "type": "deposit", "amount": 500.0, "date": "2026-06-01", "event_id": "2"},
    ]
    result = compute_bankroll_growth(accounts, events)
    overall = result["overall"]
    assert overall["total_deposited"] == pytest.approx(1000.0)
    assert overall["current_balance"] == pytest.approx(1050.0)
    assert overall["betting_pnl"] == pytest.approx(50.0)
    assert overall["growth_pct"] == pytest.approx(0.05)

    pb = result["per_book"]
    assert pb["BetMGM"]["growth_pct"] == pytest.approx(0.2)
    assert pb["FanDuel"]["growth_pct"] == pytest.approx(-0.1)


def test_no_deposit_growth_is_none():
    """A book with a balance but no events → growth_pct is None (no cost basis)."""
    accounts = {"Bovada": {"current_balance": 300.0}}
    result = compute_bankroll_growth(accounts, [])
    assert result["overall"]["growth_pct"] is None
    assert result["per_book"]["Bovada"]["growth_pct"] is None


def test_loss_scenario():
    """$1000 deposited, balance dropped to $800 → -20% growth."""
    accounts = {"DraftKings": {"current_balance": 800.0}}
    events = [
        {"book": "DraftKings", "type": "deposit", "amount": 1000.0, "date": "2026-04-01", "event_id": "1"}
    ]
    result = compute_bankroll_growth(accounts, events)
    overall = result["overall"]
    assert overall["betting_pnl"] == pytest.approx(-200.0)
    assert overall["growth_pct"] == pytest.approx(-0.2)


# ── Per-book baseline reset (E9.17 Phase 2) ───────────────────────────────────

def _baseline(accounts, events, book):
    """Mimic reset_book_baseline's marker without touching DynamoDB."""
    dep = sum(float(e["amount"]) for e in events
              if e["book"] == book and e["type"] == "deposit")
    wd = sum(float(e["amount"]) for e in events
             if e["book"] == book and e["type"] == "withdrawal")
    bal = float(accounts[book]["current_balance"])
    accounts[book] = {
        "current_balance": bal,
        "baseline": {
            "basis": bal,
            "deposited_offset": dep,
            "withdrawn_offset": wd,
            "reset_at": "2026-06-29T00:00:00+00:00",
        },
    }


def test_reset_baseline_zeroes_growth():
    """After a reset, growth restarts at 0% from the snapshot balance."""
    accounts = {"BetMGM": {"current_balance": 600.0}}
    events = [
        {"book": "BetMGM", "type": "deposit", "amount": 500.0, "date": "2026-06-01", "event_id": "1"},
    ]
    _baseline(accounts, events, "BetMGM")
    pb = compute_bankroll_growth(accounts, events)["per_book"]["BetMGM"]
    assert pb["growth_pct"] == pytest.approx(0.0)
    assert pb["betting_pnl"] == pytest.approx(0.0)
    assert pb["total_deposited"] == pytest.approx(600.0)  # new cost basis
    assert pb["baseline_reset_at"] == "2026-06-29T00:00:00+00:00"


def test_reset_baseline_then_win():
    """Reset at $600, win to $700 → +16.67% growth on the new $600 basis."""
    accounts = {"BetMGM": {"current_balance": 600.0}}
    events = [
        {"book": "BetMGM", "type": "deposit", "amount": 500.0, "date": "2026-06-01", "event_id": "1"},
    ]
    _baseline(accounts, events, "BetMGM")
    accounts["BetMGM"]["current_balance"] = 700.0  # later win
    pb = compute_bankroll_growth(accounts, events)["per_book"]["BetMGM"]
    assert pb["betting_pnl"] == pytest.approx(100.0)
    assert pb["growth_pct"] == pytest.approx(round(100 / 600, 6))


def test_reset_baseline_idempotent():
    """Re-basing an unchanged book a second time yields the same result."""
    accounts = {"FanDuel": {"current_balance": 450.0}}
    events = [
        {"book": "FanDuel", "type": "deposit", "amount": 500.0, "date": "2026-06-01", "event_id": "1"},
    ]
    _baseline(accounts, events, "FanDuel")
    first = compute_bankroll_growth(accounts, events)["per_book"]["FanDuel"]
    # Second reset off the already-rebased state, events unchanged.
    _baseline(accounts, events, "FanDuel")
    second = compute_bankroll_growth(accounts, events)["per_book"]["FanDuel"]
    assert first["growth_pct"] == pytest.approx(0.0)
    assert second["growth_pct"] == pytest.approx(0.0)
    assert first["total_deposited"] == pytest.approx(second["total_deposited"])


def test_reset_baseline_new_deposit_counts():
    """Deposits recorded after a reset still extend the (re-based) cost basis."""
    accounts = {"Bovada": {"current_balance": 300.0}}
    events = [
        {"book": "Bovada", "type": "deposit", "amount": 300.0, "date": "2026-06-01", "event_id": "1"},
    ]
    _baseline(accounts, events, "Bovada")
    # Post-reset: deposit $100 more, balance now $400 (no betting yet).
    events.append({"book": "Bovada", "type": "deposit", "amount": 100.0, "date": "2026-06-29", "event_id": "2"})
    accounts["Bovada"]["current_balance"] = 400.0
    pb = compute_bankroll_growth(accounts, events)["per_book"]["Bovada"]
    assert pb["total_deposited"] == pytest.approx(400.0)
    assert pb["betting_pnl"] == pytest.approx(0.0)
    assert pb["growth_pct"] == pytest.approx(0.0)


def test_reset_one_book_does_not_affect_other():
    """Resetting BetMGM leaves FanDuel's growth untouched in the overall roll-up."""
    accounts = {
        "BetMGM": {"current_balance": 600.0},
        "FanDuel": {"current_balance": 450.0},
    }
    events = [
        {"book": "BetMGM", "type": "deposit", "amount": 500.0, "date": "2026-06-01", "event_id": "1"},
        {"book": "FanDuel", "type": "deposit", "amount": 500.0, "date": "2026-06-01", "event_id": "2"},
    ]
    _baseline(accounts, events, "BetMGM")
    result = compute_bankroll_growth(accounts, events)
    assert result["per_book"]["BetMGM"]["growth_pct"] == pytest.approx(0.0)
    assert result["per_book"]["FanDuel"]["growth_pct"] == pytest.approx(-0.1)
