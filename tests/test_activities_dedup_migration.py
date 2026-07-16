import re
import unittest
from pathlib import Path


MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "2026-07-16-ctm-activities-dedup.sql"
)


class ActivitiesDedupMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = MIGRATION.read_text()
        cls.normalized_sql = re.sub(r"\s+", " ", cls.sql)

    def _view_body(self, view_name):
        marker = f"{view_name}` AS"
        body = self.sql.split(marker, 1)[1]
        if view_name.endswith("_90d"):
            return body.split("-- MANUAL-RUN-ONLY", 1)[0]
        return body.split("CREATE OR REPLACE VIEW `data-etl-to-bigquery.ctm_data.activities_combined_deduped_90d` AS", 1)[0]

    def _manual_run_only_block(self):
        return self.sql.split("-- MANUAL-RUN-ONLY", 1)[1]

    def test_expected_views_are_created(self):
        self.assertIn("activities_combined_deduped`", self.sql)
        self.assertIn("activities_combined_deduped_90d`", self.sql)

    def test_partition_key_contains_existing_identity_fallbacks(self):
        self.assertIn("CONCAT(CAST(account_id AS STRING), '|id|', CAST(id AS STRING))", self.sql)
        self.assertIn("CONCAT(CAST(account_id AS STRING), '|sid|', sid)", self.sql)
        self.assertIn("CAST(called_at AS STRING)", self.sql)
        self.assertIn("IFNULL(caller_number, '')", self.sql)

    def test_ordering_clauses_appear_in_exact_sequence(self):
        clauses = [
            "CASE WHEN LOWER(TRIM(CAST(status AS STRING))) IN ('in progress','in-progress','ringing','queued','initiated') OR LOWER(TRIM(CAST(call_status AS STRING))) IN ('in progress','in-progress','ringing','queued','initiated') THEN 0 ELSE 1 END DESC",
            "(NULLIF(TRIM(CAST(tracking_label AS STRING)), '') IS NOT NULL) DESC",
            "SAFE_CAST(duration AS FLOAT64) DESC NULLS LAST",
            "SAFE_CAST(talk_time AS FLOAT64) DESC NULLS LAST",
            "SAFE_CAST(processed_at AS TIMESTAMP) DESC NULLS LAST",
            "SAFE_CAST(batch_number AS INT64) DESC NULLS LAST",
            "_candidate_priority DESC",
            "_candidate_loaded_at DESC NULLS LAST",
            "FARM_FINGERPRINT(TO_JSON_STRING(t))",
        ]

        for view_name in ("activities_combined_deduped", "activities_combined_deduped_90d"):
            with self.subTest(view_name=view_name):
                normalized_body = re.sub(r"\s+", " ", self._view_body(view_name))
                positions = [normalized_body.index(clause) for clause in clauses]
                self.assertEqual(positions, sorted(positions))

    def test_call_status_participates_in_in_flight_classification(self):
        expected_case = (
            "CASE WHEN LOWER(TRIM(CAST(status AS STRING))) IN "
            "('in progress','in-progress','ringing','queued','initiated') "
            "OR LOWER(TRIM(CAST(call_status AS STRING))) IN "
            "('in progress','in-progress','ringing','queued','initiated') "
            "THEN 0 ELSE 1 END DESC"
        )

        for view_name in ("activities_combined_deduped", "activities_combined_deduped_90d"):
            with self.subTest(view_name=view_name):
                normalized_body = re.sub(r"\s+", " ", self._view_body(view_name))
                self.assertIn(expected_case, normalized_body)

    def test_historical_dml_call_status_participates_in_in_flight_classification(self):
        expected_case = (
            "-- CASE WHEN LOWER(TRIM(CAST(status AS STRING))) IN "
            "('in progress','in-progress','ringing','queued','initiated') "
            "-- OR LOWER(TRIM(CAST(call_status AS STRING))) IN "
            "('in progress','in-progress','ringing','queued','initiated') "
            "-- THEN 0 ELSE 1 END DESC"
        )
        normalized_block = re.sub(r"\s+", " ", self._manual_run_only_block())

        self.assertIn(expected_case, normalized_block)

    def test_historical_dml_is_strictly_older_than_90_days(self):
        normalized_block = re.sub(r"\s+", " ", self._manual_run_only_block())

        self.assertIn(
            "-- Rows with NULL called_at belong to the active hourly 90-day refresh path.",
            normalized_block,
        )
        self.assertIn(
            "-- WHERE DATE(called_at) < DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)",
            normalized_block,
        )
        self.assertNotIn("called_at IS NULL", normalized_block)

    def test_90d_predicate_is_inside_each_source_branch(self):
        view_90d = self._view_body("activities_combined_deduped_90d")
        predicate = (
            "WHERE (DATE(called_at) >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY) "
            "OR called_at IS NULL)"
        )

        self.assertEqual(view_90d.count(predicate), 3)

    def test_union_distinct_absent_from_new_view_bodies(self):
        view_bodies = (
            self._view_body("activities_combined_deduped")
            + self._view_body("activities_combined_deduped_90d")
        )

        self.assertNotIn("UNION DISTINCT", view_bodies)
        self.assertIn("UNION ALL", view_bodies)


if __name__ == "__main__":
    unittest.main()
