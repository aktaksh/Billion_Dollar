from __future__ import annotations

import unittest
from dataclasses import dataclass
from datetime import timedelta, timezone
from datetime import datetime as dt

from app.services.options_chain_planner import (
    _is_five_dollar_multiple,
    _listed_five_dollar_strikes,
    plan_scan_scope,
)


@dataclass
class _PlannerCfg:
    min_dte: int = 14
    max_dte: int = 35
    strike_interval: float = 5.0
    max_contracts_per_scan: int = 200
    allow_exceed_max_contracts: bool = False
    strikes_below: int = 8
    strikes_above: int = 12
    max_expiries: int = 4
    strike_pct_range: float = 0.10


def _expiry(days: int) -> str:
    return (dt.now(timezone.utc).date() + timedelta(days=days)).isoformat()


def _listed_grid(low: int, high: int) -> list[float]:
    return [float(s) for s in range(low, high + 1)]


class OptionsChainPlannerTests(unittest.TestCase):
    def _cfg(self, **overrides: object) -> _PlannerCfg:
        base = _PlannerCfg()
        return base.__class__(**{**base.__dict__, **overrides})

    def test_listed_five_dollar_multiples_only(self) -> None:
        raw = [700.0, 701.0, 705.0, 706.0, 727.0, 730.0]
        self.assertEqual(_listed_five_dollar_strikes(raw), [700.0, 705.0, 730.0])

    def test_spot_700_selects_eight_below_twelve_above(self) -> None:
        cfg = self._cfg()
        expiries = [_expiry(d) for d in (14, 21, 28, 35, 42, 49)]
        listed = _listed_grid(600, 800)
        plan = plan_scan_scope(spot=700.0, all_expiries=expiries, all_strikes=listed, cfg=cfg)
        below = [s for s in plan.strikes if s < 700.0]
        above = [s for s in plan.strikes if s > 700.0]
        self.assertEqual(len(below), 8)
        self.assertEqual(len(above), 12)
        self.assertEqual(below, [660.0, 665.0, 670.0, 675.0, 680.0, 685.0, 690.0, 695.0])
        self.assertEqual(above[0], 705.0)
        self.assertEqual(above[-1], 760.0)
        self.assertEqual(len(plan.expiries), 4)
        self.assertEqual(plan.planned_contracts, 160)
        self.assertTrue(all(_is_five_dollar_multiple(s) for s in plan.strikes))

    def test_spot_736_selects_nearest_listed_strikes(self) -> None:
        cfg = self._cfg()
        listed = _listed_grid(650, 850)
        plan = plan_scan_scope(spot=736.68, all_expiries=[_expiry(21)], all_strikes=listed, cfg=cfg)
        below = [s for s in plan.strikes if s < 736.68]
        above = [s for s in plan.strikes if s > 736.68]
        self.assertEqual(len(below), 8)
        self.assertEqual(len(above), 12)
        self.assertEqual(below[-1], 735.0)
        self.assertEqual(above[0], 740.0)

    def test_dte_window_excludes_out_of_range_expiries(self) -> None:
        cfg = self._cfg()
        expiries = [_expiry(7), _expiry(14), _expiry(28), _expiry(50)]
        plan = plan_scan_scope(spot=700.0, all_expiries=expiries, all_strikes=[700.0, 705.0], cfg=cfg)
        self.assertEqual(plan.expiries, [_expiry(14), _expiry(28)])

    def test_truncation_drops_expiries_when_over_cap(self) -> None:
        cfg = self._cfg(max_contracts_per_scan=40, max_expiries=4)
        expiries = [_expiry(d) for d in (14, 21, 28, 35)]
        listed = _listed_grid(670, 750)
        plan = plan_scan_scope(spot=700.0, all_expiries=expiries, all_strikes=listed, cfg=cfg)
        self.assertLessEqual(plan.planned_contracts, 40)
        self.assertTrue(any("dropped expiry" in n for n in plan.truncation_notes))

    def test_never_exceeds_cap_when_allow_exceed_false(self) -> None:
        cfg = self._cfg(max_contracts_per_scan=200, allow_exceed_max_contracts=False)
        expiries = [_expiry(d) for d in range(14, 43, 7)]
        listed = _listed_grid(600, 850)
        plan = plan_scan_scope(spot=700.0, all_expiries=expiries, all_strikes=listed, cfg=cfg)
        self.assertLessEqual(plan.planned_contracts, 200)
        self.assertEqual(plan.planned_contracts, 160)


if __name__ == "__main__":
    unittest.main()
