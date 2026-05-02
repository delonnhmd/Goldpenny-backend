import os
import unittest
import uuid
from decimal import Decimal
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ["DATABASE_URL"] = "postgresql://goldpenny:goldpenny@localhost:5432/goldpenny_test"

from app.api.gameplay import (
    GameplayActionPreviewRequest,
    GameplayActionRequest,
    execute_gameplay_action,
    get_gameplay_actions,
    get_gameplay_loop_bundle,
    preview_gameplay_action,
)
from app.db.database import Base
from app.models.daily_settlement_log import DailySettlementLog
from app.models.contribution_event import ContributionEvent
from app.models.gameplay_transaction import GameplayTransaction
from app.models.game_state import GameState
from app.models.job_action import JobAction
from app.models.macro_state import MacroState
from app.models.player import Player
from app.models.player_career import PlayerCareer
from app.models.player_daily_state import PlayerDailyState
from app.models.player_employment_state import PlayerEmploymentState
from app.models.player_housing_state import PlayerHousingState
from app.models.player_job_progression import PlayerJobProgression
from app.models.player_transaction_log import PlayerTransactionLog
from app.models.shift_salary_audit_log import ShiftSalaryAuditLog
from app.models.user import User
from app.models.xgp_transaction import XGPTransaction
from app.services.job_key_service import supported_main_job_keys_text


class JobSelectionFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:", future=True)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine, future=True)
        Base.metadata.create_all(
            bind=self.engine,
            tables=[
                User.__table__,
                Player.__table__,
                GameState.__table__,
                MacroState.__table__,
                DailySettlementLog.__table__,
                PlayerCareer.__table__,
                PlayerDailyState.__table__,
                PlayerEmploymentState.__table__,
                PlayerHousingState.__table__,
                PlayerJobProgression.__table__,
                JobAction.__table__,
                GameplayTransaction.__table__,
                PlayerTransactionLog.__table__,
                ShiftSalaryAuditLog.__table__,
                XGPTransaction.__table__,
                ContributionEvent.__table__,
            ],
        )
        self.db = self.SessionLocal()

        user = User(email=f"job-flow-{uuid.uuid4()}@example.com", hashed_password="hashed")
        self.db.add(user)
        self.db.flush()

        self.db.add(GameState(current_day=1, day_status="open"))
        self.db.add(
            MacroState(
                day_number=1,
                inflation=Decimal("2.0"),
                interest_rate=Decimal("4.0"),
                unemployment=Decimal("6.0"),
                oil_index=Decimal("100.0"),
                consumer_confidence=Decimal("50.0"),
                supply_chain_stress=Decimal("0.0"),
                is_active=True,
            )
        )

        self.player = Player(
            user_id=str(user.id),
            display_name="Job Flow Player",
            main_job=None,
            cash=Decimal("1000.00"),
            stress=20,
            health=90,
            fatigue=5.0,
            hours_available=16,
            skill_level=1,
            region="suburban",
            rideshare_reliability=Decimal("0.95"),
        )
        self.db.add(self.player)
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def test_switch_job_persists_canonical_main_job_and_allows_clock_in(self) -> None:
        switch_result = execute_gameplay_action(
            str(self.player.id),
            GameplayActionRequest(
                action_key="switch_job",
                parameters={"new_job_key": "delivery"},
            ),
            db=self.db,
        )
        self.db.refresh(self.player)

        self.assertTrue(bool(switch_result["success"]))
        self.assertEqual(self.player.main_job, "delivery")
        self.assertEqual(
            switch_result["raw_result"]["job_progress"]["job_key"],
            "delivery",
        )

        actions_payload = get_gameplay_actions(str(self.player.id), db=self.db)
        self.assertEqual(actions_payload["debug_meta"]["current_job_key"], "delivery")
        action_keys = {
            str(item.get("action_key") or "")
            for item in [
                *(actions_payload.get("recommended_actions") or []),
                *(actions_payload.get("available_actions") or []),
                *(actions_payload.get("blocked_actions") or []),
            ]
        }
        self.assertIn("work_shift", action_keys)

        work_result = execute_gameplay_action(
            str(self.player.id),
            GameplayActionRequest(
                action_key="work_shift",
                parameters={"job_name": "delivery", "hours_worked": 6, "shift_type": "standard_shift"},
            ),
            db=self.db,
        )
        self.db.refresh(self.player)

        self.assertTrue(bool(work_result["success"]))
        self.assertEqual(self.player.main_job, "delivery")
        self.assertFalse(bool(self.player.main_shift_active_flag))
        self.assertEqual(
            work_result["raw_result"]["work_state"]["shift_job_name"],
            "delivery",
        )

    def test_switch_job_rejects_legacy_alias_with_clear_error(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            execute_gameplay_action(
                str(self.player.id),
                GameplayActionRequest(
                    action_key="switch_job",
                    parameters={"new_job_key": "delivery_driver"},
                ),
                db=self.db,
            )

        self.assertEqual(ctx.exception.status_code, 422)
        self.assertEqual(
            ctx.exception.detail,
            f"Invalid job key: delivery_driver. Expected one of: {supported_main_job_keys_text()}",
        )

    def test_actions_fetch_repairs_missing_main_job_from_career_state(self) -> None:
        career = PlayerCareer(
            player_id=self.player.id,
            current_job_key="warehouse_operator",
        )
        self.db.add(career)
        self.db.commit()
        self.db.refresh(self.player)

        actions_payload = get_gameplay_actions(str(self.player.id), db=self.db)
        self.db.refresh(self.player)

        self.assertEqual(self.player.main_job, "warehouse_operator")
        self.assertEqual(actions_payload["debug_meta"]["current_job_key"], "warehouse_operator")
        self.assertEqual(
            actions_payload["work_state"]["job_sync_status"],
            "auto_repaired",
        )

        work_result = execute_gameplay_action(
            str(self.player.id),
            GameplayActionRequest(
                action_key="work_shift",
                parameters={"job_name": "warehouse_operator", "hours_worked": 6, "shift_type": "standard_shift"},
            ),
            db=self.db,
        )
        self.db.refresh(self.player)

        self.assertTrue(bool(work_result["success"]))
        self.assertEqual(self.player.main_job, "warehouse_operator")
        self.assertFalse(bool(self.player.main_shift_active_flag))

    def test_work_shift_preview_uses_testing_timer_copy_and_unit_cost(self) -> None:
        self.player.main_job = "delivery"
        self.db.commit()

        with patch.dict(os.environ, {"GAMEPLAY_TESTING_MODE": "1"}, clear=False):
            preview = preview_gameplay_action(
                str(self.player.id),
                GameplayActionPreviewRequest(
                    action_key="work_shift",
                    parameters={"job_name": "delivery", "hours_worked": 6, "shift_type": "standard_shift"},
                ),
                db=self.db,
            )

        self.assertIn("resolves immediately", preview["summary"])
        self.assertEqual(preview["expected_time_impact"]["text"], "-6 units")
        self.assertEqual(preview["debug_meta"]["shift_window"], "15 minutes")
        self.assertEqual(preview["debug_meta"]["time_cost_units"], 6)

    def test_loop_bundle_uses_shared_authoritative_state_contract(self) -> None:
        with patch(
            "app.api.gameplay.get_playable_player_summary",
            return_value={
                "cash_xgp": float(self.player.cash),
                "debt_xgp": float(self.player.debt_xgp or 0),
                "stress": int(self.player.stress or 0),
                "health": int(self.player.health or 100),
                "credit_score": int(self.player.credit_score or 650),
                "region": str(self.player.region or "suburban"),
            },
        ), patch("app.api.gameplay.get_player_latest_daily_brief", return_value=None), patch(
            "app.api.gameplay.build_economy_presentation_summary",
            return_value=None,
        ), patch(
            "app.api.gameplay.get_player_job_summary",
            return_value={"current_job_code": self.player.main_job or "banker"},
        ):
            bundle = get_gameplay_loop_bundle(str(self.player.id), db=self.db)

        top_level = bundle["authoritative_state"]
        dashboard_state = bundle["dashboard"]["authoritative_state"]
        action_hub_state = bundle["action_hub"]["authoritative_state"]

        self.assertIn("game_time", bundle)
        self.assertIn("game_time", bundle["dashboard"])
        self.assertIn("run_status", bundle)
        self.assertIn("run_status", bundle["dashboard"])
        self.assertEqual(bundle["run_status"]["run_status"], "active")
        self.assertTrue(bundle["run_status"]["can_continue"])
        self.assertEqual(bundle["game_time"]["timezone"], "America/Chicago")
        self.assertIn("next_settlement_at", bundle["game_time"])
        self.assertIn("next_morning_brief_at", bundle["game_time"])
        self.assertEqual(top_level["player_id"], str(self.player.id))
        self.assertEqual(dashboard_state["player_id"], str(self.player.id))
        self.assertEqual(action_hub_state["player_id"], str(self.player.id))
        self.assertEqual(top_level["current_job_key"], dashboard_state["current_job_key"])
        self.assertEqual(top_level["current_job_key"], action_hub_state["current_job_key"])
        self.assertEqual(
            top_level["player_state"]["stress"],
            action_hub_state["player_state"]["stress"],
        )
        self.assertEqual(
            top_level["rideshare_state"]["can_rideshare"],
            dashboard_state["rideshare_state"]["can_rideshare"],
        )

    def test_execute_action_returns_updated_authoritative_state(self) -> None:
        result = execute_gameplay_action(
            str(self.player.id),
            GameplayActionRequest(
                action_key="switch_job",
                parameters={"new_job_key": "delivery"},
            ),
            db=self.db,
        )

        updated_state = result["updated_state"]
        raw_updated_state = result["raw_result"]["updated_state"]

        self.assertTrue(bool(result["success"]))
        self.assertEqual(updated_state["player_id"], str(self.player.id))
        self.assertEqual(updated_state["current_job_key"], "delivery")
        self.assertEqual(raw_updated_state["current_job_key"], "delivery")
        self.assertEqual(
            updated_state["shift_state"]["can_start_shift"],
            raw_updated_state["shift_state"]["can_start_shift"],
        )

    def test_switch_job_rejects_locked_progression_role_until_requirements_are_met(self) -> None:
        self.player.last_settled_day = 1
        self.db.commit()

        with self.assertRaises(HTTPException) as locked_ctx:
            execute_gameplay_action(
                str(self.player.id),
                GameplayActionRequest(
                    action_key="switch_job",
                    parameters={"new_job_key": "warehouse_operator"},
                ),
                db=self.db,
            )

        self.assertEqual(locked_ctx.exception.status_code, 422)
        self.assertIn("still locked", str(locked_ctx.exception.detail).lower())

        self.player.skill_level = 2
        self.db.add(
            PlayerJobProgression(
                player_id=self.player.id,
                job_key="delivery",
                skill_level=1,
                xp_total=30,
                xp=30,
                xp_to_next_level=100,
                promotion_tier="Junior",
                shifts_completed=3,
            )
        )
        self.db.commit()

        result = execute_gameplay_action(
            str(self.player.id),
            GameplayActionRequest(
                action_key="switch_job",
                parameters={"new_job_key": "warehouse_operator"},
            ),
            db=self.db,
        )
        self.db.refresh(self.player)

        self.assertTrue(bool(result["success"]))
        self.assertEqual(self.player.main_job, "warehouse_operator")

    def test_work_shift_focus_bonus_adds_bonus_xp_to_shift_result(self) -> None:
        execute_gameplay_action(
            str(self.player.id),
            GameplayActionRequest(
                action_key="switch_job",
                parameters={"new_job_key": "delivery"},
            ),
            db=self.db,
        )

        result = execute_gameplay_action(
            str(self.player.id),
            GameplayActionRequest(
                action_key="work_shift",
                parameters={
                    "job_name": "delivery",
                    "hours_worked": 6,
                    "shift_type": "standard_shift",
                    "shift_focus": "quality",
                },
            ),
            db=self.db,
        )

        shift_task = result["raw_result"]["shift_task"]
        completed_shift = result["raw_result"]["completed_shift"]

        self.assertTrue(bool(result["success"]))
        self.assertEqual(shift_task["choice_key"], "quality")
        self.assertEqual(int(shift_task["bonus_xp"]), 6)
        self.assertGreaterEqual(int(completed_shift["xp_gained"]), 156)
        self.assertIn("Protect Quality bonus", result["result_summary"])


if __name__ == "__main__":
    unittest.main()
