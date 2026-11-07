"""Tests for Agent 3 (Migration Engineering)."""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "migration_planner"))

import orchestrator
from agents.migration_engineering import MigrationEngineeringAgent
from agents.migration_engineering.context_builder import ContextBuilder
from agents.migration_engineering.schema_generator import SchemaGenerator


class TestMigrationEngineering(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sample_dir = ROOT / "tests" / "fixtures" / "sample-app"
        cls.analysis = orchestrator.analyze_sample(generate_graph=True)

    def setUp(self):
        self.temp_ws = Path(tempfile.mkdtemp(prefix="test-engineering-"))
        self.agent = MigrationEngineeringAgent(workspace_base_dir=self.temp_ws)

    def tearDown(self):
        if self.temp_ws.exists():
            shutil.rmtree(self.temp_ws, ignore_errors=True)

    def test_schema_generator_extracts_user_and_post_models(self):
        builder = ContextBuilder(self.sample_dir)
        models = builder.extract_models()

        self.assertIn("User", models)
        self.assertIn("Post", models)

        user_model = models["User"]
        self.assertIn("name", user_model.fields)
        self.assertTrue(user_model.fields["name"].is_required)
        self.assertIn("email", user_model.fields)
        self.assertTrue(user_model.fields["email"].is_unique)
        self.assertTrue(user_model.has_timestamps)

        post_model = models["Post"]
        self.assertIn("title", post_model.fields)
        self.assertIn("author", post_model.fields)
        self.assertEqual(post_model.fields["author"].relation_model, "User")

        generator = SchemaGenerator(models)
        prisma_schema = generator.generate()

        self.assertIn("datasource db {", prisma_schema)
        self.assertIn('provider = "postgresql"', prisma_schema)
        self.assertIn("model User {", prisma_schema)
        self.assertIn("model Post {", prisma_schema)
        self.assertIn("posts Post[]", prisma_schema)
        self.assertIn("@relation(fields: [authorId], references: [id])", prisma_schema)

    def test_run_engineering_dry_run_produces_diffs_without_modifying_source(self):
        analysis_data = self.analysis.model_dump(by_alias=True)
        result = self.agent.run(self.sample_dir, analysis_data, dry_run=True)

        self.assertEqual(result.status, "dry_run")
        self.assertTrue(result.diff_available)
        self.assertGreaterEqual(result.files_created, 2)  # schema.prisma, prisma.js
        self.assertGreaterEqual(result.files_modified, 1)  # userService.js

        # Verify sample dir was not modified
        user_service = (self.sample_dir / "src" / "services" / "userService.js").read_text()
        self.assertIn("User.findById(id)", user_service)
        self.assertIn("require('../models/User')", user_service)

    def test_run_engineering_transforms_queries(self):
        analysis_data = self.analysis.model_dump(by_alias=True)
        result = self.agent.run(self.sample_dir, analysis_data, dry_run=False)

        # Check created files in workspace
        ws_path = Path(result.workspace_dir)
        self.assertTrue((ws_path / "prisma" / "schema.prisma").is_file())
        self.assertTrue((ws_path / "src" / "config" / "prisma.js").is_file())

        # Check modified service in workspace
        mod_user_service = (ws_path / "src" / "services" / "userService.js").read_text()
        self.assertIn("prisma.user.findUnique({ where: { id }, include: { posts: true } })", mod_user_service)
        self.assertIn("prisma.user.findMany({ orderBy: { createdAt: 'desc' } })", mod_user_service)
        self.assertIn("prisma.user.create({ data })", mod_user_service)
        self.assertIn("prisma.user.delete({ where: { id } })", mod_user_service)
        self.assertIn("require('../config/prisma')", mod_user_service)

    def test_aggregate_operation_marked_for_manual_review(self):
        analysis_data = self.analysis.model_dump(by_alias=True)
        result = self.agent.run(self.sample_dir, analysis_data, dry_run=False)

        # Post aggregate should not be blindly replaced with broken code
        ws_path = Path(result.workspace_dir)
        mod_post_service = (ws_path / "src" / "services" / "postService.js").read_text()
        self.assertIn("Post.aggregate([", mod_post_service)

        # Verify aggregate is tracked as review required
        post_fc = next((f for f in result.files if "postService.js" in f.file), None)
        if post_fc:
            self.assertTrue(post_fc.review_required)

    def test_run_engineering_with_task_id_filter(self):
        analysis_data = self.analysis.model_dump(by_alias=True)
        plan_tasks = analysis_data["plan"]["tasks"]
        # Find findById task for userService
        user_tasks = [t["id"] for t in plan_tasks if "userService.js" in t.get("file", "")]
        self.assertTrue(len(user_tasks) > 0)

        result = self.agent.run(self.sample_dir, analysis_data, task_ids=[user_tasks[0]], dry_run=False)
        self.assertIn(result.status, ["completed", "partial"])


if __name__ == "__main__":
    unittest.main()
