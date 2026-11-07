
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from migration.planner import create_migration_plan


class TestMigrationPlanner(unittest.TestCase):

    def test_find_by_id_creates_conversion_task(self):
        findings = [
            {
                "file": "services/userService.js",
                "line": 12,
                "pattern": "User.findById()",
                "operation": "findById",
            }
        ]

        plan = create_migration_plan(findings)

        self.assertEqual(plan["summary"]["findings_received"], 1)
        self.assertEqual(plan["summary"]["tasks_created"], 1)
        self.assertEqual(
            plan["tasks"][0]["target_operation"],
            "findUnique",
        )

    def test_aggregate_creates_high_priority_blocker(self):
        findings = [
            {
                "file": "services/reportService.js",
                "line": 30,
                "pattern": "Model.aggregate()",
                "operation": "aggregate",
            }
        ]

        plan = create_migration_plan(findings)

        self.assertEqual(plan["summary"]["blockers_found"], 1)
        self.assertEqual(plan["blockers"][0]["severity"], "high")
        self.assertEqual(plan["tasks"][0]["priority"], "high")

    def test_empty_findings(self):
        plan = create_migration_plan([])

        self.assertEqual(plan["summary"]["findings_received"], 0)
        self.assertEqual(plan["summary"]["tasks_created"], 0)
        self.assertEqual(plan["summary"]["blockers_found"], 0)

    
    def test_unknown_operation_creates_warning(self):
        findings = [
            {
                "file": "services/customService.js",
                "line": 8,
                "pattern": "customQuery()",
                "operation": "customQuery",
            }
        ]

        plan = create_migration_plan(findings)

        self.assertEqual(plan["summary"]["warnings_count"], 1)
        self.assertEqual(plan["warnings"][0]["operation"], "customQuery")

    def test_multiple_blockers_are_detected(self):
        findings = [
            {
                "file": "services/reportService.js",
                "line": 30,
                "pattern": "Model.aggregate() with ObjectId",
                "operation": "aggregate",
            }
        ]

        plan = create_migration_plan(findings)

        self.assertEqual(plan["summary"]["blockers_found"], 2)
        self.assertEqual(
            {blocker["keyword"] for blocker in plan["blockers"]},
            {"aggregate", "ObjectId"},
        )

    def test_invalid_finding_is_skipped(self):
        findings = [
            "this is not a dictionary",
            {
                "file": "services/userService.js",
                "line": 12,
                "pattern": "User.findById()",
                "operation": "findById",
            },
        ]

        plan = create_migration_plan(findings)

        self.assertEqual(plan["summary"]["findings_received"], 2)
        self.assertEqual(plan["summary"]["findings_processed"], 1)
        self.assertEqual(plan["summary"]["tasks_created"], 1)
        self.assertEqual(plan["summary"]["warnings_count"], 1)


if __name__ == "__main__":
    unittest.main()
 